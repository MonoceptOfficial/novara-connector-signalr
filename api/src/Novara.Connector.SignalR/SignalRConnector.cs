/// <summary>
/// SignalRConnector — Internal NovaraSignalRHub Integration
///
/// PURPOSE: Self-describing connector for the NovaraSignalRHub service (port :5020).
/// Receives client lifecycle events (connected, disconnected, joined group, left group)
/// from the hub and emits normalized ConnectorDataEvents. Consumed by modules that care
/// about real-time presence, notification delivery tracking, and session health (Activities,
/// Notifications, Collaborate).
///
/// AUTH: Internal shared-secret via X-SignalR-Token header. Hub is co-deployed inside
/// the customer trust boundary so HMAC isn't required.
///
/// WEBHOOK FLOW:
///   1. Hub POSTs event to /api/v1/connectors/connector.signalr/webhook
///   2. Gateway routes to this connector's HandleWebhookAsync
///   3. We validate the shared secret
///   4. We parse either client or group event shape from X-SignalR-Event header
///   5. We emit one ConnectorDataEvent
/// </summary>
using System.Net.Http.Json;
using System.Text.Json;
using Novara.Module.SDK;
using Novara.Connector.SignalR.Constants;
using Novara.Connector.SignalR.Models;

namespace Novara.Connector.SignalR;

public class SignalRConnector : ConnectorBase
{
    private static readonly JsonSerializerOptions JsonOpts = new()
    {
        PropertyNameCaseInsensitive = true
    };

    public override ConnectorManifest Manifest => new()
    {
        Id = "connector.signalr",
        Name = "SignalR Hub",
        Version = "1.0.0",
        Author = "Monocept",
        Description = "Internal NovaraSignalRHub — real-time presence + client lifecycle events. Internal gRPC/HTTP transport; no HMAC (trust boundary).",
        Icon = "radio",
        Source = "Official",
        Category = "Internal",
        AuthType = "apikey",
        DocumentationUrl = "https://docs.novara.io/connectors/signalr",
        SupportsImport = false,
        SupportsExport = false,
        SupportsWebhook = true,
        SupportedEventTypes = new()
        {
            SignalREvents.ClientConnected,
            SignalREvents.ClientDisconnected,
            SignalREvents.GroupJoined,
            SignalREvents.GroupLeft
        },
        TargetModules = new() { "novara.activities", "novara.notifications", "novara.collaborate" },
        ConfigFields = new()
        {
            new() { Key = "hubUrl", Label = "SignalR Hub URL", Type = "url",
                    Required = true, DefaultValue = "https://localhost:5020",
                    Description = "Base URL of the internal NovaraSignalRHub service.",
                    Group = "Connection", Order = 1 },
            new() { Key = "apiKey", Label = "Internal API Key",
                    Type = "password", Required = true, Sensitive = true,
                    Description = "Shared secret the hub sends in the X-SignalR-Token header on outbound webhook calls.",
                    Group = "Authentication", Order = 2 }
        }
    };

    public override async Task<ConnectorTestResult> TestConnectionAsync(ConnectorConfig config, CancellationToken ct = default)
    {
        var hubUrl = config.Values.GetValueOrDefault("hubUrl", "");
        if (string.IsNullOrEmpty(hubUrl))
            return new ConnectorTestResult { Success = false, Message = "SignalR Hub URL is required." };

        try
        {
            using var http = new HttpClient { Timeout = TimeSpan.FromSeconds(5) };
            var response = await http.GetAsync($"{hubUrl.TrimEnd('/')}/health", ct);
            if (!response.IsSuccessStatusCode)
            {
                return new ConnectorTestResult
                {
                    Success = false,
                    Message = $"SignalR Hub health returned {(int)response.StatusCode}."
                };
            }

            var health = await response.Content.ReadFromJsonAsync<JsonElement>(JsonOpts, ct);
            var version = health.TryGetProperty("version", out var v) ? v.GetString() : "unknown";
            return new ConnectorTestResult
            {
                Success = true,
                Message = $"SignalR Hub reachable at {hubUrl}. Version: {version}.",
                ServerVersion = version
            };
        }
        catch (HttpRequestException ex)
        {
            return new ConnectorTestResult { Success = false, Message = $"Cannot reach SignalR Hub at {hubUrl}: {ex.Message}" };
        }
        catch (TaskCanceledException)
        {
            return new ConnectorTestResult { Success = false, Message = $"Timeout reaching SignalR Hub at {hubUrl}." };
        }
    }

    public override Task<ConnectorResult> HandleWebhookAsync(
        ConnectorConfig config, string payload, Dictionary<string, string> headers, CancellationToken ct = default)
    {
        var result = new ConnectorResult { Success = true };

        // Shared-secret auth
        var expected = config.Values.GetValueOrDefault("apiKey", "");
        var presented = headers.GetValueOrDefault("X-SignalR-Token",
                        headers.GetValueOrDefault("x-signalr-token", ""));
        if (!string.IsNullOrEmpty(expected) && !string.Equals(presented, expected, StringComparison.Ordinal))
        {
            result.Success = false;
            result.Message = "Invalid X-SignalR-Token.";
            return Task.FromResult(result);
        }

        var eventHeader = headers.GetValueOrDefault("X-SignalR-Event",
                          headers.GetValueOrDefault("x-signalr-event", SignalREvents.HeaderClient));

        try
        {
            if (string.Equals(eventHeader, SignalREvents.HeaderClient, StringComparison.OrdinalIgnoreCase))
            {
                result.Events.AddRange(ParseClientEvent(payload));
            }
            else if (string.Equals(eventHeader, SignalREvents.HeaderGroup, StringComparison.OrdinalIgnoreCase))
            {
                result.Events.AddRange(ParseGroupEvent(payload));
            }
            else
            {
                result.Message = $"Event type '{eventHeader}' not handled.";
            }

            result.RecordsProcessed = result.Events.Count;
        }
        catch (JsonException ex)
        {
            result.Success = false;
            result.Message = $"Failed to parse SignalR payload: {ex.Message}";
        }

        return Task.FromResult(result);
    }

    private static List<ConnectorDataEvent> ParseClientEvent(string payload)
    {
        var ev = JsonSerializer.Deserialize<SignalRClientEvent>(payload, JsonOpts);
        if (ev?.Client == null) return new();

        var eventType = ev.Action switch
        {
            "connected"    => SignalREvents.ClientConnected,
            "disconnected" => SignalREvents.ClientDisconnected,
            _              => null
        };
        if (eventType == null) return new();

        return new()
        {
            new ConnectorDataEvent
            {
                ConnectorId = "connector.signalr",
                EventType = eventType,
                EntityType = "client",
                ExternalId = ev.Client.ConnectionId,
                ProductId = ev.Client.ProductId ?? 0,
                TimestampUtc = ev.Client.TimestampUtc,
                Data = new Dictionary<string, object>
                {
                    ["connectionId"] = ev.Client.ConnectionId,
                    ["userId"]       = ev.Client.UserId,
                    ["productId"]    = ev.Client.ProductId ?? 0,
                    ["userAgent"]    = ev.Client.UserAgent ?? "",
                    ["ipAddress"]    = ev.Client.IpAddress ?? ""
                }
            }
        };
    }

    private static List<ConnectorDataEvent> ParseGroupEvent(string payload)
    {
        var ev = JsonSerializer.Deserialize<SignalRGroupEvent>(payload, JsonOpts);
        if (ev == null) return new();

        var eventType = ev.Action switch
        {
            "joined" => SignalREvents.GroupJoined,
            "left"   => SignalREvents.GroupLeft,
            _        => null
        };
        if (eventType == null) return new();

        return new()
        {
            new ConnectorDataEvent
            {
                ConnectorId = "connector.signalr",
                EventType = eventType,
                EntityType = "group",
                ExternalId = $"{ev.GroupName}:{ev.ConnectionId}",
                TimestampUtc = ev.TimestampUtc,
                Data = new Dictionary<string, object>
                {
                    ["connectionId"] = ev.ConnectionId,
                    ["userId"]       = ev.UserId,
                    ["groupName"]    = ev.GroupName
                }
            }
        };
    }
}

/// <summary>
/// SignalRPayloads — Event shapes from NovaraSignalRHub.
///
/// RELATIONSHIPS: Mirror of the hub's outbound event DTOs. Update together.
/// </summary>
namespace Novara.Connector.SignalR.Models;

public class SignalRClientEvent
{
    public string Action { get; set; } = "";              // connected | disconnected
    public SignalRClient Client { get; set; } = new();
}

public class SignalRClient
{
    public string ConnectionId { get; set; } = "";
    public int UserId { get; set; }
    public int? ProductId { get; set; }
    public string? UserAgent { get; set; }
    public string? IpAddress { get; set; }
    public DateTime TimestampUtc { get; set; } = DateTime.UtcNow;
}

public class SignalRGroupEvent
{
    public string Action { get; set; } = "";              // joined | left
    public string ConnectionId { get; set; } = "";
    public int UserId { get; set; }
    public string GroupName { get; set; } = "";
    public DateTime TimestampUtc { get; set; } = DateTime.UtcNow;
}

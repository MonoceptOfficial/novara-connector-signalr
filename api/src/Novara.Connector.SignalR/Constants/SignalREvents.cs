/// <summary>
/// SignalREvents — Event types this connector emits.
/// </summary>
namespace Novara.Connector.SignalR.Constants;

public static class SignalREvents
{
    public const string ClientConnected    = "signalr.client.connected";
    public const string ClientDisconnected = "signalr.client.disconnected";
    public const string GroupJoined        = "signalr.group.joined";
    public const string GroupLeft          = "signalr.group.left";

    // X-SignalR-Event header values
    public const string HeaderClient = "client";
    public const string HeaderGroup  = "group";
}

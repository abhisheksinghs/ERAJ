import { getTenantSlug, fetchFromBackend } from "@/lib/tenant";

interface Room {
  id: number;
  number: string;
  capacity: number;
}

export default async function HostelPage() {
  const tenantSlug = getTenantSlug();

  if (!tenantSlug) {
    return <div className="notice notice--no-tenant">No tenant resolved for this request.</div>;
  }

  const result = await fetchFromBackend<Room[]>(tenantSlug, "/api/hostel/rooms/");

  if (!result.ok) {
    return <div className="notice">{result.error}</div>;
  }

  const rooms = result.data;

  return (
    <div>
      <h1>Hostel — {tenantSlug}</h1>
      {rooms.length === 0 ? (
        <p>No rooms set up yet for this institution.</p>
      ) : (
        <table>
          <thead>
            <tr>
              <th>Room</th>
              <th>Capacity</th>
            </tr>
          </thead>
          <tbody>
            {rooms.map((room) => (
              <tr key={room.id}>
                <td>{room.number}</td>
                <td>{room.capacity}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

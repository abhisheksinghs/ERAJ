import { redirect } from "next/navigation";

import { getAccessToken } from "@/lib/auth";
import { fetchFromBackend, getTenantSlug } from "@/lib/tenant";

interface Room {
  id: number;
  number: string;
  capacity: number;
  occupied: number;
  available_beds: number;
}

export default async function HostelPage() {
  const tenantSlug = getTenantSlug();
  if (!tenantSlug) {
    return <div className="notice notice--no-tenant">No tenant resolved for this request.</div>;
  }

  const token = getAccessToken();
  if (!token) redirect("/login");

  const result = await fetchFromBackend<Room[]>(tenantSlug, "/api/hostel/rooms/", token);
  if (!result.ok && result.status === 401) redirect("/login");
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
              <th>Occupied</th>
              <th>Free</th>
            </tr>
          </thead>
          <tbody>
            {rooms.map((room) => (
              <tr key={room.id}>
                <td>{room.number}</td>
                <td>{room.capacity}</td>
                <td>{room.occupied}</td>
                <td>{room.available_beds}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

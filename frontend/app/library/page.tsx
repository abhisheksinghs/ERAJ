import { redirect } from "next/navigation";

import { StatusNotice } from "@/app/_components/StatusNotice";
import { getAccessToken } from "@/lib/auth";
import { fetchFromBackend, getTenantSlug } from "@/lib/tenant";

interface Book {
  id: number;
  title: string;
  author: string;
  isbn: string;
  copies_total: number;
  copies_available: number;
}

export default async function LibraryPage() {
  const tenantSlug = getTenantSlug();
  if (!tenantSlug) {
    return <div className="notice notice--no-tenant">No tenant resolved for this request.</div>;
  }

  const token = getAccessToken();
  if (!token) redirect("/login");

  const result = await fetchFromBackend<Book[]>(tenantSlug, "/api/library/books/", token);
  if (!result.ok && result.status === 401) redirect("/login");
  if (!result.ok) {
    // 402 / 403 are the plan/subscription model working as designed — show the
    // specific message rather than a generic error.
    return <StatusNotice result={result} />;
  }

  const books = result.data;

  return (
    <div>
      <h1>Library — {tenantSlug}</h1>
      {books.length === 0 ? (
        <p>No books catalogued yet for this institution.</p>
      ) : (
        <table>
          <thead>
            <tr>
              <th>Title</th>
              <th>Author</th>
              <th>ISBN</th>
              <th>Available</th>
            </tr>
          </thead>
          <tbody>
            {books.map((book) => (
              <tr key={book.id}>
                <td>{book.title}</td>
                <td>{book.author}</td>
                <td>{book.isbn}</td>
                <td>
                  {book.copies_available} / {book.copies_total}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

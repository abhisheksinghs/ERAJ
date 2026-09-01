import { getTenantSlug, fetchFromBackend } from "@/lib/tenant";

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

  const result = await fetchFromBackend<Book[]>(tenantSlug, "/api/library/books/");

  if (!result.ok) {
    // 402 and 403 are not bugs — they're the plan/subscription model working
    // as designed (see apps/core/middleware.py in the backend). Every
    // module page must handle these two states explicitly instead of
    // falling through to a generic error, since they're the most common
    // "error" a real user of this platform will ever see.
    return <div className="notice">{result.error}</div>;
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

import credits from "../data/photoCredits.json";

export default function Credits() {
  const rows = Object.entries(credits).sort(([a], [b]) => a.localeCompare(b));
  return (
    <div className="wrap section">
      <div className="section-head">
        <h2>Photo credits</h2>
        <p>
          Destination photos come from Wikimedia Commons under Creative Commons or public-domain licences. Hotel
          images are generic illustrations, because the demo hotels are fictional.
        </p>
      </div>
      <div className="card credits">
        <table>
          <thead>
            <tr><th>Used as</th><th>Title</th><th>Author</th><th>Licence</th></tr>
          </thead>
          <tbody>
            {rows.map(([key, c]) => (
              <tr key={key}>
                <td>{key}</td>
                <td><a href={c.source} target="_blank" rel="noreferrer">{c.title}</a></td>
                <td>{c.author}</td>
                <td>{c.license_url ? <a href={c.license_url} target="_blank" rel="noreferrer">{c.license}</a> : c.license}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

import type { Citation } from "../api";

export default function Citations({ items }: { items: Citation[] }) {
  if (!items.length) return null;
  return (
    <div className="citations">
      <div className="citations-label">Citas</div>
      <ul>
        {items.map((c, i) => (
          <li key={i}>
            <span className="cite-section">{c.section || "sin sección"}</span>
            <span className="cite-page">p. {c.page}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

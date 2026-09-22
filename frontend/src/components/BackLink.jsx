import { useLocation, useNavigate } from "react-router-dom";

/**
 * A visible "Back" for every page. It goes to the page you came from, and to `fallback` when this page was opened
 * directly (a bookmark, a new tab, or an installed app with no browser back button). A link can say where you came
 * from with `state={{ from: "Tonight" }}`, and the button then reads "Back to Tonight".
 */
export default function BackLink({ fallback = "/", label }) {
  const navigate = useNavigate();
  const { state, key } = useLocation();
  const canGoBack = key !== "default";
  const text = label || (state?.from ? `Back to ${state.from}` : "Back");
  return (
    <button type="button" className="backlink" onClick={() => (canGoBack ? navigate(-1) : navigate(fallback))}>
      <span aria-hidden="true">←</span> {text}
    </button>
  );
}

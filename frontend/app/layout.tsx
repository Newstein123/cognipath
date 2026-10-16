import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Cognith",
  description: "Learn what you need, not everything.",
};

// Runs before first paint, so the page never flashes the wrong theme. A saved choice
// ("light" | "dark") wins; otherwise the system preference applies and is followed live.
// <html data-theme> is what the CSS reads; data-theme-choice is what the selector shows.
// window.__cognithApplyTheme(animate) re-applies after the selector saves a choice.
const THEME_SCRIPT = `(function () {
  var KEY = "cognith-theme", root = document.documentElement;
  var dark = window.matchMedia("(prefers-color-scheme: dark)");
  var still = window.matchMedia("(prefers-reduced-motion: reduce)");
  var timer;
  function apply(animate) {
    var choice = null;
    try { choice = localStorage.getItem(KEY); } catch (e) {}
    if (choice !== "light" && choice !== "dark") choice = "system";
    var theme = choice === "system" ? (dark.matches ? "dark" : "light") : choice;
    if (animate && !still.matches && root.dataset.theme && root.dataset.theme !== theme) {
      root.classList.add("theme-switching");
      clearTimeout(timer);
      timer = setTimeout(function () { root.classList.remove("theme-switching"); }, 260);
    }
    root.dataset.theme = theme;
    root.dataset.themeChoice = choice;
    window.dispatchEvent(new Event("cognith-theme"));
  }
  apply(false);
  window.__cognithApplyTheme = apply;
  dark.addEventListener("change", function () { apply(true); });
  window.addEventListener("storage", function (e) { if (e.key === KEY) apply(true); });
})();`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    // The theme attributes are set by the script before React hydrates.
    <html lang="en" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_SCRIPT }} />
      </head>
      <body>{children}</body>
    </html>
  );
}

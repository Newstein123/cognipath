/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
  // Lets a second dev server (e.g. a course pack on another port) run from this folder.
  distDir: process.env.NEXT_DIST_DIR || ".next",
};
export default nextConfig;

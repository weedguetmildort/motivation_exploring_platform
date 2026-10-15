// frontend/pages/_app.tsx
import StudyShell from "../components/StudyShell";
import type { AppProps } from "next/app";
import "../styles/globals.css";
import "katex/dist/katex.min.css";

export default function App({ Component, pageProps }: AppProps) {
  return <StudyShell><Component {...pageProps} /></StudyShell>;
}

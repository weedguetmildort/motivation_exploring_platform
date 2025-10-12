import type { AppProps } from "next/app";
import "../styles/globals.css"; // Tailwind entry

export default function App({ Component, pageProps }: AppProps) {
  return <Component {...pageProps} />;
}

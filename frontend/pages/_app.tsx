import type { AppProps } from "next/app";
import "../styles/globals.css";
// import "katex/dist/katex.min.css";

export default function App({ Component, pageProps }: AppProps) {
  return <Component {...pageProps} />;
}

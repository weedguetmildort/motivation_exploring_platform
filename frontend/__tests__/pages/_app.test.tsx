import { render, screen } from "@testing-library/react";
import type { AppProps } from "next/app";
import App from "../../pages/_app";

function DummyComponent({ greeting }: { greeting: string }) {
  return <div>{greeting}</div>;
}

describe("App", () => {
  it("renders the active page component with its pageProps", () => {
    const props = {
      Component: DummyComponent,
      pageProps: { greeting: "hello" },
    } as unknown as AppProps;

    render(<App {...props} />);
    expect(screen.getByText("hello")).toBeInTheDocument();
  });
});

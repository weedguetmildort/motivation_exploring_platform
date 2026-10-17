import { render, screen } from "@testing-library/react";
import Disclaimer from "../../components/Disclaimer";

describe("Disclaimer", () => {
  it("renders the provided group, institution, supervisor and contact email", () => {
    render(
      <Disclaimer
        groupName="Research Group"
        institution="University"
        contactEmail="contact@example.com"
        supervisor="Dr. Smith"
      />
    );

    expect(screen.getByText(/Research Group/)).toBeInTheDocument();
    expect(screen.getByText(/University/)).toBeInTheDocument();
    expect(screen.getByText(/Dr. Smith/)).toBeInTheDocument();

    const link = screen.getByRole("link", { name: "contact@example.com" });
    expect(link).toHaveAttribute("href", "mailto:contact@example.com");
  });
});

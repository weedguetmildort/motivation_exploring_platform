import { render, screen, fireEvent } from "@testing-library/react";
import PageHeader from "../../components/PageHeader";

describe("PageHeader", () => {
  it("renders the title and calls onLogout when Logout is clicked", () => {
    const onLogout = jest.fn();
    render(<PageHeader title="My Title" onLogout={onLogout} />);

    expect(screen.getByText("My Title")).toBeInTheDocument();
    fireEvent.click(screen.getByText("Logout"));
    expect(onLogout).toHaveBeenCalled();
  });

  it("renders the subtitle when provided", () => {
    render(<PageHeader title="Title" subtitle="Sub" onLogout={jest.fn()} />);
    expect(screen.getByText("Sub")).toBeInTheDocument();
  });

  it("does not render a subtitle when not provided", () => {
    const { container } = render(<PageHeader title="Title" onLogout={jest.fn()} />);
    expect(container.querySelector("p.page-subtitle")).toBeNull();
  });

  it("renders a Profile button and calls onProfile when clicked", () => {
    const onProfile = jest.fn();
    render(<PageHeader title="Title" onLogout={jest.fn()} onProfile={onProfile} />);
    fireEvent.click(screen.getByText("Profile"));
    expect(onProfile).toHaveBeenCalled();
  });

  it("renders a Dashboard button and calls onDashboard when clicked", () => {
    const onDashboard = jest.fn();
    render(<PageHeader title="Title" onLogout={jest.fn()} onDashboard={onDashboard} />);
    fireEvent.click(screen.getByText("Dashboard"));
    expect(onDashboard).toHaveBeenCalled();
  });

  it("does not render Profile or Dashboard buttons when not provided", () => {
    render(<PageHeader title="Title" onLogout={jest.fn()} />);
    expect(screen.queryByText("Profile")).not.toBeInTheDocument();
    expect(screen.queryByText("Dashboard")).not.toBeInTheDocument();
  });

  it("applies an extra className to the header", () => {
    const { container } = render(
      <PageHeader title="Title" onLogout={jest.fn()} className="shrink-0" />
    );
    expect(container.querySelector("header")?.className).toContain("shrink-0");
  });
});

import { describe, expect, it } from "vitest";
import { dotify, extractPlusTag } from "./gmail";
import { randomLocal } from "./security";

describe("gmail helpers", () => {
  it("extracts plus tag", () => {
    expect(extractPlusTag("user+abc123@gmail.com")).toBe("abc123");
  });
  it("random local looks like a readable name", () => {
    expect(randomLocal()).toMatch(/^[a-z]+\.[a-z]+\d{2}$/);
  });
  it("dotify keeps chars", () => {
    expect(dotify("abc").replace(/\./g, "")).toBe("abc");
  });
});

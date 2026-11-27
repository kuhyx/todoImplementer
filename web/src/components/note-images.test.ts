import { describe, expect, it } from "vitest";

import { renderCard } from "@/components/card";
import { noteImages, tileImage } from "@/components/note-images";
import { makeCards, NOW } from "@/test/fixtures";

const [base] = makeCards();
const card = { ...base!, images: [{ file: "1.jpg", folder: "3d6cd2ea-de63" }, { file: "2.png", folder: "f-2" }] };

describe("note images", () => {
  it("[T2535] the drawer shows every image as a thumbnail linking to the full image", () => {
    const row = noteImages(card)!;
    const links = [...row.querySelectorAll("a")];
    expect(links.map((a) => a.getAttribute("href"))).toEqual(["/api/image/3d6cd2ea-de63/1.jpg", "/api/image/f-2/2.png"]);
    expect(links.every((a) => a.target === "_blank" && a.querySelector("img") !== null)).toBe(true);
  });

  it("[T2535] the tile shows the first image, a card without images shows none", () => {
    expect(tileImage(card)?.getAttribute("src")).toBe("/api/image/3d6cd2ea-de63/1.jpg");
    expect(renderCard(card, NOW).querySelectorAll("img.card-thumb")).toHaveLength(1);
    expect(tileImage(base!)).toBeNull();
    expect(noteImages(base!)).toBeNull();
  });
});

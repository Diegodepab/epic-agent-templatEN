#!/usr/bin/env node
/**
 * extract-colors.cjs
 *
 * Extract dominant colors from an image and compare against brand palette.
 * Uses pure Node.js without external image processing dependencies.
 *
 * For full color extraction from images, integrate with ai-multimodal skill
 * or use ImageMagick via shell commands.
 *
 * Usage:
 *   node extract-colors.cjs <image-path>
 *   node extract-colors.cjs <image-path> --brand-file <path>
 *   node extract-colors.cjs --palette  # Show brand palette from guidelines
 *
 * Integration:
 *   For image color analysis, use: ai-multimodal skill or ImageMagick
 *   magick <image> -colors 10 -depth 8 -format "%c" histogram:info:
 */

const fs = require("fs");
const path = require("path");

// Default brand guidelines path
const DEFAULT_GUIDELINES_PATH = "docs/brand-guidelines.md";

/**
 * Extract hex colors from markdown content
 */
function extractHexColors(text) {
  const hexPattern = /#[0-9A-Fa-f]{6}\b/g;
  return [...new Set(text.match(hexPattern) || [])];
}

/**
 * Parse brand guidelines for color palette
 */
function parseBrandColors(guidelinesPath) {
  const resolvedPath = path.isAbsolute(guidelinesPath)
    ? guidelinesPath
    : path.join(process.cwd(), guidelinesPath);

  if (!fs.existsSync(resolvedPath)) {
    return null;
  }

  const content = fs.readFileSync(resolvedPath, "utf-8");

  const palette = {
    primary: [],
    secondary: [],
    neutral: [],
    semantic: [],
    all: [],
  };

  // Extract colors from different sections
  const sections = [
    { name: "primary", regex: /### Primary[\s\S]*?(?=###|##|$)/i },
    { name: "secondary", regex: /### Secondary[\s\S]*?(?=###|##|$)/i },
    { name: "neutral", regex: /### Neutral[\s\S]*?(?=###|##|$)/i },
    { name: "semantic", regex: /### Semantic[\s\S]*?(?=###|##|$)/i },
  ];

  sections.forEach(({ name, regex }) => {
    const match = content.match(regex);
    if (match) {
      const colors = extractHexColors(match[0]);
      palette[name] = colors;
      palette.all.push(...colors);
    }
  });

  // Dedupe all
  palette.all = [...new Set(palette.all)];

  return palette;
}

/**
 * Convert hex to RGB
 */
function hexToRgb(hex) {
  const result = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex);
  return result
    ? {
        r: parseInt(result[1], 16),
        g: parseInt(result[2], 16),
        b: parseInt(result[3], 16),
      }
    : null;
}

/**
 * Convert RGB to hex
 */
function rgbToHex(r, g, b) {
  return (
    "#" +
    [r, g, b]
      .map((x) => {
        const hex = Math.round(x).toString(16);
        return hex.length === 1 ? "0" + hex : hex;
      })
      .join("")
      .toUpperCase()
  );
}

/**
 * Calculate color distance (Euclidean in RGB space)
 */
function colorDistance(color1, color2) {
  const rgb1 = typeof color1 === "string" ? hexToRgb(color1) : color1;
  const rgb2 = typeof color2 === "string" ? hexToRgb(color2) : color2;

  if (!rgb1 || !rgb2) return Infinity;

  return Math.sqrt(
    Math.pow(rgb1.r - rgb2.r, 2) +
      Math.pow(rgb1.g - rgb2.g, 2) +
      Math.pow(rgb1.b - rgb2.b, 2)
  );
}

/**
 * Find nearest brand color
 */
function findNearestBrandColor(color, brandColors) {
  let nearest = null;
  let minDistance = Infinity;

  brandColors.forEach((brandColor) => {
    const distance = colorDistance(color, brandColor);
    if (distance < minDistance) {
      minDistance = distance;
      nearest = brandColor;
    }
  });

  return { color: nearest, distance: minDistance };
}

/**
 * Calculate brand compliance percentage
 * Distance threshold: 50 (out of max ~441 for RGB)
 */
function calculateCompliance(extractedColors, brandColors, threshold = 50) {
  if (!extractedColors || extractedColors.length === 0) return 100;
  if (!brandColors || brandColors.length === 0) return 0;

  let matchCount = 0;

  extractedColors.forEach((color) => {
    const nearest = findNearestBrandColor(color, brandColors);
    if (nearest.distance <= threshold) {
      matchCount++;
    }
  });

  return Math.round((matchCount / extractedColors.length) * 100);
}

/**
 * Generate ImageMagick command for color extraction
 */
function generateImageMagickCommand(imagePath, numColors = 10) {
  return `magick "${imagePath}" -colors ${numColors} -depth 8 -format "%c" histogram:info:`;
}

/**
 * Parse ImageMagick histogram output to extract colors
 */
function parseImageMagickOutput(output) {
  const colors = [];
  const lines = output.trim().split("\n");

  lines.forEach((line) => {
    // Match pattern like: 12345: (255,128,64) #FF8040 srgb(255,128,64)
    const hexMatch = line.match(/#([0-9A-Fa-f]{6})/);
    const countMatch = line.match(/^\s*(\d+):/);

    if (hexMatch) {
      colors.push({
        hex: "#" + hexMatch[1].toUpperCase(),
        count: countMatch ? parseInt(countMatch[1]) : 0,
      });
    }
  });

  // Sort by count (most common first)
  colors.sort((a, b) => b.count - a.count);

  return colors;
}

/**
 * Display brand palette
 */
function displayPalette(palette) {
  console.log("\n" + "=".repeat(50));
  console.log("BRAND COLOR PALETTE");
  console.log("=".repeat(50));

  if (palette.primary.length > 0) {
    console.log("\nPrimary Colors:");
    palette.primary.forEach((c) => console.log(`  ${c}`));
  }

  if (palette.secondary.length > 0) {
    console.log("\nSecondary Colors:");
    palette.secondary.forEach((c) => console.log(`  ${c}`));
  }

  if (palette.neutral.length > 0) {
    console.log("\nNeutral Colors:");
    palette.neutral.forEach((c) => console.log(`  ${c}`));
  }

  if (palette.semantic.length > 0) {
    console.log("\nSemantic Colors:");
    palette.semantic.forEach((c) => console.log(`  ${c}`));
  }

  console.log("\n" + "=".repeat(50));
  console.log(`Total: ${palette.all.length} colors in brand palette`);
  console.log("=".repeat(50) + "\n");
}

/**
 * Scan a directory of frontend source/stylesheet files for active hex, rgb, hsl, and CSS custom properties.
 */
function scanDirectoryColors(dirPath) {
  const exts = new Set([".css", ".scss", ".tsx", ".jsx", ".ts", ".js", ".svelte", ".astro", ".html", ".vue"]);
  const ignore = new Set(["node_modules", ".git", "dist", "build", ".next"]);
  const hexColors = new Set();
  const cssVars = new Set();
  let filesScanned = 0;

  function walk(cur) {
    for (const entry of fs.readdirSync(cur, { withFileTypes: true })) {
      if (entry.isDirectory()) {
        if (!ignore.has(entry.name)) walk(path.join(cur, entry.name));
      } else if (entry.isFile() && exts.has(path.extname(entry.name))) {
        filesScanned += 1;
        const text = fs.readFileSync(path.join(cur, entry.name), "utf-8");
        for (const h of text.match(/#[0-9A-Fa-f]{3,8}\b/g) || []) hexColors.add(h.toLowerCase());
        for (const m of text.matchAll(/(--[a-zA-Z0-9-]+)\s*:\s*([^;}\n]+)/g)) {
          cssVars.add(`${m[1]}: ${m[2].trim()}`);
        }
      }
    }
  }
  walk(dirPath);
  return {
    directory: dirPath,
    filesScanned,
    colors: [...hexColors].sort(),
    cssVariables: [...cssVars].sort(),
  };
}

/**
 * Main function
 */
function main() {
  const args = process.argv.slice(2);
  if (args.includes("--help") || args.includes("-h")) {
    console.log(
      "Usage:\n" +
      "  node extract-colors.cjs <src-dir> [--json]                  # Scan directory for active colors & CSS vars\n" +
      "  node extract-colors.cjs <image-path> [--brand-file <md>]    # Generate ImageMagick extraction & brand check\n" +
      "  node extract-colors.cjs --palette [--brand-file <md>]       # Print parsed brand palette"
    );
    return;
  }

  const jsonOutput = args.includes("--json");
  const showPalette = args.includes("--palette");
  const brandFileIdx = args.indexOf("--brand-file");
  const brandFile =
    brandFileIdx !== -1 ? args[brandFileIdx + 1] : DEFAULT_GUIDELINES_PATH;
  const brandFileValue = brandFileIdx !== -1 ? args[brandFileIdx + 1] : null;
  const dirFlagIdx = args.indexOf("--dir");
  const dirFlagValue = dirFlagIdx !== -1 ? args[dirFlagIdx + 1] : null;
  const targetArg = dirFlagValue || args.find(
    (a) => !a.startsWith("--") && a !== "-h" && a !== brandFileValue && a !== dirFlagValue
  );

  if (targetArg && !showPalette) {
    const resolvedTarget = path.isAbsolute(targetArg) ? targetArg : path.join(process.cwd(), targetArg);
    if (!fs.existsSync(resolvedTarget)) {
      console.error(`Target path not found: ${resolvedTarget}`);
      process.exit(1);
    }
    if (fs.statSync(resolvedTarget).isDirectory()) {
      const summary = scanDirectoryColors(resolvedTarget);
      if (jsonOutput) {
        console.log(JSON.stringify(summary, null, 2));
      } else {
        console.log(`[extract-colors] Scanned ${summary.filesScanned} file(s) in ${summary.directory}`);
        console.log(`Colors (${summary.colors.length}): ${summary.colors.join(", ") || "none"}`);
        console.log(`CSS Variables (${summary.cssVariables.length}): ${summary.cssVariables.slice(0, 12).join("; ") || "none"}`);
      }
      return;
    }
  }

  const imagePath = targetArg;

  // Load brand palette
  const brandPalette = parseBrandColors(brandFile);

  if (!brandPalette) {
    console.error(`Brand guidelines not found at: ${brandFile}`);
    console.error(`Create brand guidelines or specify path with --brand-file`);
    process.exit(1);
  }

  // Show palette mode
  if (showPalette || !imagePath) {
    if (jsonOutput) {
      console.log(JSON.stringify(brandPalette, null, 2));
    } else {
      displayPalette(brandPalette);

      if (!imagePath) {
        console.log("To extract colors from an image:");
        console.log("  node extract-colors.cjs <image-path>");
        console.log("\nOr use ImageMagick directly:");
        console.log('  magick image.png -colors 10 -depth 8 -format "%c" histogram:info:');
      }
    }
    return;
  }

  // Resolve image path
  const resolvedPath = path.isAbsolute(imagePath)
    ? imagePath
    : path.join(process.cwd(), imagePath);

  if (!fs.existsSync(resolvedPath)) {
    console.error(`Image not found: ${resolvedPath}`);
    process.exit(1);
  }

  // Generate extraction instructions
  const result = {
    image: resolvedPath,
    brandPalette: brandPalette,
    extractionCommand: generateImageMagickCommand(resolvedPath),
    instructions: [
      "1. Run the ImageMagick command to extract colors:",
      `   ${generateImageMagickCommand(resolvedPath)}`,
      "",
      "2. Or use an image-analysis skill (e.g. ai-multimodal, if installed) to extract the 10 most dominant colors as hex values",
      "",
      "3. Then compare extracted colors against brand palette",
    ],
    complianceCheck: {
      threshold: 50,
      description:
        "Colors within distance 50 (RGB space) are considered brand-compliant",
      brandColors: brandPalette.all,
    },
  };

  if (jsonOutput) {
    console.log(JSON.stringify(result, null, 2));
  } else {
    console.log("\n" + "=".repeat(60));
    console.log("COLOR EXTRACTION HELPER");
    console.log("=".repeat(60));
    console.log(`\nImage: ${result.image}`);
    console.log(`\nBrand Colors: ${brandPalette.all.length} colors loaded`);
    console.log("\nTo extract colors from this image:\n");
    result.instructions.forEach((line) => console.log(line));
    console.log("\n" + "=".repeat(60));

    // Show brand palette for reference
    console.log("\nBrand Palette Reference:");
    console.log(`  Primary: ${brandPalette.primary.join(", ") || "none"}`);
    console.log(`  Secondary: ${brandPalette.secondary.join(", ") || "none"}`);
    console.log(`  Neutral: ${brandPalette.neutral.join(", ") || "none"}`);
    console.log("=".repeat(60) + "\n");
  }
}

// Export functions for use as module
module.exports = {
  parseBrandColors,
  hexToRgb,
  rgbToHex,
  colorDistance,
  findNearestBrandColor,
  calculateCompliance,
  parseImageMagickOutput,
};

// Run if called directly
if (require.main === module) {
  main();
}

/* Fixed blend grid: select on one seed, freeze, evaluate on two unused seeds. */
"use strict";
const fs = require("node:fs"),
  path = require("node:path"),
  assert = require("node:assert/strict");
const { execFileSync } = require("node:child_process");
module.exports = async function ({ page, out, root }) {
  const reports = [],
    output = path.join(out, "tradeoff");
  fs.rmSync(output, { recursive: true, force: true });
  fs.mkdirSync(output, { recursive: true });
  for (const seed of [20261017, 20261018, 20261019, 20261020, 20261021]) {
    for (const scenario of ["shapes", "pixel-art", "gradient"]) {
      const sources = await page.evaluate(
        ({ seed, scenario }) => {
          let state = seed >>> 0;
          const random = () =>
            (state = (Math.imul(1664525, state) + 1013904223) >>> 0) /
            4294967296;
          const make = (size) => {
            const c = document.createElement("canvas");
            c.width = c.height = size;
            return c;
          };
          const ref = make(128),
            t = ref.getContext("2d");
          t.fillStyle = "#ffffff";
          t.fillRect(0, 0, 128, 128);
          const colors = ["#087d79", "#efbe4c", "#d05b78", "#163b3b"];
          if (scenario === "shapes") {
            for (let i = 0; i < 6; i++) {
              t.fillStyle = colors[Math.floor(random() * colors.length)];
              const x = 8 + random() * 92,
                y = 8 + random() * 92,
                r = 5 + random() * 20;
              t.beginPath();
              t.arc(x, y, r, 0, Math.PI * 2);
              t.fill();
            }
          } else if (scenario === "pixel-art") {
            for (let y = 0; y < 16; y++)
              for (let x = 0; x < 16; x++) {
                t.fillStyle = colors[Math.floor(random() * colors.length)];
                t.fillRect(x * 8, y * 8, 8, 8);
              }
          } else {
            const g = t.createLinearGradient(0, 0, 128, 128);
            g.addColorStop(0, colors[Math.floor(random() * 4)]);
            g.addColorStop(
              0.3 + random() * 0.4,
              colors[Math.floor(random() * 4)],
            );
            g.addColorStop(1, colors[Math.floor(random() * 4)]);
            t.fillStyle = g;
            t.fillRect(0, 0, 128, 128);
          }
          const low = make(16),
            l = low.getContext("2d");
          l.imageSmoothingEnabled = true;
          l.imageSmoothingQuality = "high";
          l.drawImage(ref, 0, 0, 16, 16);
          const up = (smooth) => {
            const c = make(128),
              v = c.getContext("2d");
            v.imageSmoothingEnabled = smooth;
            v.imageSmoothingQuality = "high";
            v.drawImage(low, 0, 0, 128, 128);
            return c.toDataURL("image/png");
          };
          return {
            reference: ref.toDataURL("image/png"),
            nearest: up(false),
            smooth: up(true),
          };
        },
        { seed, scenario },
      );
      const dir = path.join(output, `${seed}-${scenario}`);
      fs.mkdirSync(dir);
      for (const [name, uri] of Object.entries(sources))
        fs.writeFileSync(
          path.join(dir, name + ".png"),
          Buffer.from(uri.split(",")[1], "base64"),
        );
      execFileSync(
        process.env.PYTHON || "python",
        [
          "-S",
          "image_compare.py",
          "--reference",
          path.join(dir, "reference.png"),
          "--nearest",
          path.join(dir, "nearest.png"),
          "--smooth",
          path.join(dir, "smooth.png"),
          "--out",
          path.join(dir, "variants"),
        ],
        { cwd: root, timeout: 60000 },
      );
      const report = JSON.parse(
        fs.readFileSync(path.join(dir, "variants/report.json")),
      );
      assert.equal(report.candidates.length, 11);
      reports.push({ seed, scenario, report });
    }
  }
  const train = reports.filter((r) => r.seed === 20261017);
  const aggregate = Array.from({ length: 11 }, (_, index) => ({
    index,
    ...Object.fromEntries(
      ["rgb_mae", "rgb_rmse", "balance_score"].map((metric) => [
        metric,
        train.reduce((sum, r) => sum + r.report.candidates[index][metric], 0) /
          train.length,
      ]),
    ),
  }));
  const best = (metric, max = false) =>
    [...aggregate].sort(
      (a, b) =>
        (max ? b[metric] - a[metric] : a[metric] - b[metric]) ||
        a.index - b.index,
    )[0].index;
  const frozen = {
    mae_priority: best("rgb_mae"),
    rmse_priority: best("rgb_rmse"),
    midpoint: 5,
    balanced: best("balance_score", true),
  };
  // A second, explicit policy can use the supplied fixture category. This is
  // not an image classifier, and the original global policy is retained too.
  const scenarioFrozen = Object.fromEntries(
    ["shapes", "pixel-art", "gradient"].map((scenario) => {
      const trainingCase = train.find((r) => r.scenario === scenario);
      const roles = trainingCase.report.roles;
      return [scenario, { ...roles }];
    }),
  );
  assert(reports.filter((r) => r.seed !== 20261017).length === 12);
  const result = {
    schema: "ironmate-tradeoff-seeds/1",
    candidate_grid: "k/10, k=0..10; fixed before generating these cases",
    training_seed: 20261017,
    evaluation_seeds: [20261018, 20261019, 20261020, 20261021],
    scenario_policy_fresh_seeds: [20261020, 20261021],
    scenarios: ["shapes", "pixel-art", "gradient"],
    policy:
      "equal-image means of MAE/RMSE/score; MAE weight 0.5; index breaks ties",
    exploratory: true,
    frozen_indices: frozen,
    scenario_frozen_indices: scenarioFrozen,
    scenario_policy:
      "explicit fixture category, not inferred from evaluation pixels; exploratory second policy",
    training_means: aggregate,
    cases: reports.map(({ seed, scenario, report }) => ({
      seed,
      scenario,
      role: seed === 20261017 ? "selection" : "held-out",
      input_sha256: report.input_sha256,
      pareto_indices: report.pareto_indices,
      oracle_roles: report.roles,
      all_candidates: report.candidates,
      frozen_results: Object.fromEntries(
        Object.entries(frozen).map(([name, index]) => [
          name,
          report.candidates[index],
        ]),
      ),
      scenario_frozen_results: Object.fromEntries(
        Object.entries(scenarioFrozen[scenario]).map(([name, index]) => [
          name,
          report.candidates[index],
        ]),
      ),
    })),
  };
  fs.writeFileSync(
    path.join(output, "seed-results.json"),
    JSON.stringify(result, null, 2),
  );
};

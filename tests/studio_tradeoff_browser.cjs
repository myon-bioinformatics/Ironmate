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
        require("./studio_fixtures.cjs"),
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

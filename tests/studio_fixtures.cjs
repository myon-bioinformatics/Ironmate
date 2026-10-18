// studio_fixtures.cjs
// Shared browser Canvas sources; kept identical to the original tradeoff experiment.
"use strict";
module.exports = ({ seed, scenario }) => {
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
        };

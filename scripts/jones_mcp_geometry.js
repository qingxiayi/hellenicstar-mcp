// Reuse the Mini Program's Jones presentation geometry for the MCP image.
const fs = require('fs');
const presentation = require('../assets/js/jones_presentation.js');

const input = JSON.parse(fs.readFileSync(0, 'utf8'));
const chart = presentation.build(input.jones, input.asc, input.cusps, {
  rulerChains: input.rulerChains,
  ascRuler: input.ascRuler,
  aspects: input.aspects,
});
if (!chart) throw new Error('Jones geometry unavailable');
process.stdout.write(JSON.stringify({
  pattern_zh: chart.pattern_zh,
  pattern_en: chart.pattern_en,
  state_label: chart.state_label,
  family_zh: chart.family_zh,
  span_deg: chart.span_deg,
  max_gap_deg: chart.max_gap_deg,
  occupied_signs: chart.occupied_signs,
  points: chart.points,
  occupiedFans: chart.occupiedFans,
  importantGap: chart.importantGap,
  axisLabels: chart.axisLabels,
  bowlPoles: chart.bowlPoles,
  ascLongitude: chart.ascLongitude,
  cusps: chart.cusps,
}));

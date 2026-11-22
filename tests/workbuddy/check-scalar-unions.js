// Probe legal JSON values against each discovered union in isolation. Checking
// the entire catalog catches regressions outside the two claim-verification tools.
const fs = require("node:fs");
const Ajv = require("ajv");
const baseline = new Ajv({ strict: false });
const client = new Ajv({ strict: false, coerceTypes: true });
const samples = [null, true, false, 0, 1, 4, 91.16, "", "4", "true", "placidus",
  [], [4, "4", false], {}, { a: 1, b: "4" }, { roles: { a: "parent" } }];
const tools = JSON.parse(fs.readFileSync(0, "utf8"));
let tested = 0;
for (const [name, schema] of Object.entries(tools)) {
  function visit(field, path) {
    if (!field || typeof field !== "object") return;
    if (field.anyOf || Array.isArray(field.type)) {
      const wrapper = { $defs: schema.$defs || {}, type: "object", properties: { value: field } };
      const accepts = baseline.compile(wrapper);
      const validate = client.compile(wrapper);
      for (const value of samples) {
        if (!accepts({ value })) continue;
        const original = JSON.stringify({ value });
        const args = JSON.parse(original);
        if (!validate(args) || JSON.stringify(args) !== original) {
          throw new Error(name + " " + path + " changed " + original + " to " + JSON.stringify(args));
        }
        tested++;
      }
    }
    for (const [key, child] of Object.entries(field)) visit(child, path + "/" + key);
  }
  visit(schema, "");
}
if (!tested) throw new Error("No union fields checked");
console.log(tested);

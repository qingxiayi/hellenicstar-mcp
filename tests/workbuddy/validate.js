const fs = require("node:fs");
const Ajv = require("ajv");
const { schema, args } = JSON.parse(fs.readFileSync(0, "utf8"));
const validate = new Ajv({ coerceTypes: true, strict: false }).compile(schema);
if (!validate(args)) throw new Error(JSON.stringify(validate.errors));
process.stdout.write(JSON.stringify(args));

// Extract the Bangladesh outline from Natural Earth (world-atlas, public domain) into a small
// GeoJSON file so the map needs no tile server and works offline (RULES R-SEC-4).
import { readFileSync, writeFileSync } from "node:fs";
import { feature } from "topojson-client";

const topo = JSON.parse(readFileSync(new URL("../node_modules/world-atlas/countries-10m.json", import.meta.url)));
const countries = feature(topo, topo.objects.countries);
const bd = countries.features.find((f) => f.properties.name === "Bangladesh");
if (!bd) throw new Error("Bangladesh not found in world-atlas");
const round = (c) => (typeof c[0] === "number" ? [+c[0].toFixed(3), +c[1].toFixed(3)] : c.map(round));
bd.geometry.coordinates = round(bd.geometry.coordinates);
const out = { type: "FeatureCollection", features: [{ type: "Feature", properties: { name: "Bangladesh", source: "Natural Earth via world-atlas" }, geometry: bd.geometry }] };
writeFileSync(new URL("../src/assets/bangladesh.json", import.meta.url), JSON.stringify(out));
console.log("wrote src/assets/bangladesh.json");

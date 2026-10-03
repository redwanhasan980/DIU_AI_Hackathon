// Agent risk map. Base layer is a bundled Bangladesh outline (Natural Earth) — no tile server, so the
// demo works offline (RULES.md R-SEC-4). Risk is colour + marker size + tooltip label, never colour alone.
import type { GeoJsonObject } from "geojson";
import { CircleMarker, GeoJSON, MapContainer, Tooltip } from "react-leaflet";
import { useNavigate } from "react-router-dom";
import type { AgentSummary, Lang } from "../api/types";
import bd from "../assets/bangladesh.json";
import { ACTION_LABEL, ARCHETYPE_LABEL, BAND_LABEL } from "../i18n/strings";
import { pct, taka } from "../lib/format";

const COLOR = { low: "#0ca30c", medium: "#fab219", high: "#d03b3b" } as const;
const RADIUS = { low: 4, medium: 6, high: 8 } as const;

export function NetworkMap({ agents, lang, height = 460 }: { agents: AgentSummary[]; lang: Lang; height?: number }) {
  const navigate = useNavigate();
  // draw low-risk first so high-risk markers sit on top
  const order = { low: 0, medium: 1, high: 2 } as const;
  const sorted = [...agents].sort((a, b) => order[a.risk_band] - order[b.risk_band]);
  return (
    <div className="overflow-hidden rounded-lg border border-line" style={{ height }}>
      <MapContainer
        bounds={[[20.6, 88.0], [26.65, 92.7]]}
        zoomSnap={0.25}
        minZoom={6}
        maxZoom={11}
        scrollWheelZoom={false}
        style={{ height: "100%", width: "100%" }}
        attributionControl={false}
      >
        <GeoJSON
          data={bd as unknown as GeoJsonObject}
          style={{ color: "var(--axis)", weight: 1.5, fillColor: "var(--surface-1)", fillOpacity: 1 }}
        />
        {sorted.map((a) => (
          <CircleMarker
            key={a.agent_id}
            center={[a.lat, a.lon]}
            radius={RADIUS[a.risk_band]}
            pathOptions={{ color: "var(--surface-1)", weight: 1.5, fillColor: COLOR[a.risk_band], fillOpacity: 0.9 }}
            eventHandlers={{ click: () => navigate(`/agents/${a.agent_id}`) }}
          >
            <Tooltip direction="top" offset={[0, -6]}>
              <div className="text-xs">
                <div className="font-semibold">{a.shop_name} · {a.agent_id}</div>
                <div>{a.upazila}, {a.district} — {ARCHETYPE_LABEL[lang][a.archetype]}</div>
                <div>
                  {BAND_LABEL[lang][a.risk_band]} {pct(a.p_stockout, lang)} · {ACTION_LABEL[lang][a.action]}
                  {a.amount > 0 && ` ${taka(a.amount, lang)}`}
                </div>
              </div>
            </Tooltip>
          </CircleMarker>
        ))}
      </MapContainer>
    </div>
  );
}

export function MapLegend({ lang }: { lang: Lang }) {
  return (
    <div className="mt-2 flex flex-wrap gap-4 text-xs text-ink-2">
      {(["high", "medium", "low"] as const).map((b) => (
        <span key={b} className="flex items-center gap-1.5">
          <span className="inline-block rounded-full" style={{ background: COLOR[b], width: RADIUS[b] * 2, height: RADIUS[b] * 2 }} />
          {BAND_LABEL[lang][b]}
        </span>
      ))}
      <span className="text-muted">· {lang === "bn" ? "বিস্তারিত দেখতে এজেন্টে ক্লিক করুন" : "Click an agent for details"}</span>
    </div>
  );
}

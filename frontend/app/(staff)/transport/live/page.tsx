"use client";

import "leaflet/dist/leaflet.css";

import { Alert, Card, DatePicker, Result, Space, Table, Tag, Typography } from "antd";
import dayjs, { type Dayjs } from "dayjs";
import type * as Leaflet from "leaflet";
import { useCallback, useEffect, useRef, useState } from "react";

import { UI } from "@/lib/i18n";
import { api } from "@/lib/refine/dataProvider";
import { useSession } from "@/lib/refine/session";
import { tr, type T } from "@/lib/resources";

/** Live vehicle positions (OpenStreetMap), refreshed every 15 s; a vehicle's trip for a chosen day (ADR-010). */
interface Live {
  vehicle: number; registration_no: string; route: string; route_name: string; driver: string; driver_phone: string;
  lat: string | null; lng: string | null; speed: string | null; seen_at: string | null; age_seconds: number | null;
  riders: number; capacity: number;
}
interface Point { at: string; lat: string; lng: string; speed: string }

const t = (en: string, hi: string): T => ({ en, hi });
const L = {
  title: t("Live map", "लाइव मानचित्र"), vehicle: t("Vehicle", "वाहन"), route: t("Route", "मार्ग"), driver: t("Driver", "चालक"),
  seen: t("Last position", "अंतिम स्थिति"), speed: t("Speed", "गति"), riders: t("Riders", "यात्री"),
  noGps: t("No GPS position yet", "अभी जीपीएस स्थिति नहीं"), trip: t("Trip on", "यात्रा"), pick: t("Click a vehicle to see its trip.", "यात्रा देखने के लिए वाहन चुनें।"),
  ago: t("ago", "पहले"), stale: t("over 5 min old", "5 मिनट से पुराना"),
};
const PATNA: [number, number] = [25.6093, 85.1376];

function age(s: number | null, lang: "en" | "hi") {
  if (s === null) return "—";
  if (s < 60) return `${s}s ${tr(L.ago, lang)}`;
  if (s < 3600) return `${Math.floor(s / 60)}m ${tr(L.ago, lang)}`;
  return `${Math.floor(s / 3600)}h ${tr(L.ago, lang)}`;
}

export default function LiveMap() {
  const { lang, can, allBranches, branch } = useSession();
  const box = useRef<HTMLDivElement>(null);
  const map = useRef<Leaflet.Map | null>(null);
  const layer = useRef<Leaflet.LayerGroup | null>(null);
  const tripLayer = useRef<Leaflet.LayerGroup | null>(null);
  const lib = useRef<typeof Leaflet | null>(null);
  const [rows, setRows] = useState<Live[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<number | null>(null);
  const [day, setDay] = useState<Dayjs>(dayjs());

  const draw = useCallback((data: Live[]) => {
    const Lf = lib.current;
    if (!Lf || !map.current || !layer.current) return;
    layer.current.clearLayers();
    const pts: [number, number][] = [];
    for (const v of data) {
      if (v.lat === null || v.lng === null) continue;
      const p: [number, number] = [Number(v.lat), Number(v.lng)];
      pts.push(p);
      const fresh = (v.age_seconds ?? 9999) < 300;
      Lf.circleMarker(p, { radius: 9, color: fresh ? "#1e2761" : "#9aa3b5", fillColor: fresh ? "#3b5bdb" : "#c9cedb", fillOpacity: 0.9, weight: 2 })
        .bindTooltip(`${v.registration_no} · ${v.route} · ${v.speed ?? 0} km/h`, { permanent: true, direction: "right", offset: [8, 0] })
        .on("click", () => setSelected(v.vehicle))
        .addTo(layer.current);
    }
    if (pts.length && !tripLayer.current?.getLayers().length) map.current.fitBounds(Lf.latLngBounds(pts).pad(0.3), { maxZoom: 15 });
  }, []);

  const load = useCallback(async () => {
    try {
      const data = await api.get<Live[]>("transport/reports/live");
      setRows(data);
      setError(null);
      draw(data);
    } catch (e) {
      setError((e as { message?: string }).message ?? "Error");
    }
  }, [draw]);

  useEffect(() => {
    if (allBranches || !box.current || map.current) return;
    let cancelled = false;
    void import("leaflet").then((mod) => {
      if (cancelled || !box.current) return;
      const Lf = mod.default ?? mod;
      lib.current = Lf;
      map.current = Lf.map(box.current).setView(PATNA, 12);
      Lf.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
        maxZoom: 19, attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
      }).addTo(map.current);
      layer.current = Lf.layerGroup().addTo(map.current);
      tripLayer.current = Lf.layerGroup().addTo(map.current);
      void load();
    });
    return () => {
      cancelled = true;
    };
  }, [allBranches, load]);

  useEffect(() => {
    const id = window.setInterval(() => void load(), 15000);
    return () => window.clearInterval(id);
  }, [load, branch?.id]);

  useEffect(() => {
    const Lf = lib.current;
    if (!selected || !Lf || !tripLayer.current || !map.current) return;
    void api.get<Point[]>(`transport/vehicles/${selected}/trip?date=${day.format("YYYY-MM-DD")}`).then((pts) => {
      tripLayer.current!.clearLayers();
      const line = pts.map((p) => [Number(p.lat), Number(p.lng)] as [number, number]);
      if (line.length) {
        Lf.polyline(line, { color: "#e8590c", weight: 4 }).addTo(tripLayer.current!);
        map.current!.fitBounds(Lf.latLngBounds(line).pad(0.2), { maxZoom: 16 });
      }
    });
  }, [selected, day]);

  if (!can("transport.vehicle.view")) return <Result status="403" title={tr(UI.noAccess, lang)} />;
  if (allBranches) return <Result status="info" title={tr(UI.readOnlyAll, lang)} />;

  return (
    <Space direction="vertical" size="middle" style={{ width: "100%", padding: 8 }}>
      <Typography.Title level={3} style={{ margin: 0 }}>{tr(L.title, lang)}</Typography.Title>
      {error && <Alert type="error" showIcon message={error} />}
      <Card size="small" styles={{ body: { padding: 0 } }}>
        <div ref={box} data-testid="map" style={{ height: 420, width: "100%", borderRadius: 8 }} />
      </Card>
      <Space wrap>
        <Typography.Text>{tr(L.trip, lang)}</Typography.Text>
        <DatePicker value={day} onChange={(d) => d && setDay(d)} format="DD-MM-YYYY" allowClear={false} aria-label="trip-date" />
        <Typography.Text type="secondary">{selected ? rows.find((r) => r.vehicle === selected)?.registration_no : tr(L.pick, lang)}</Typography.Text>
      </Space>
      <Table<Live> rowKey="vehicle" size="small" pagination={false} dataSource={rows}
        onRow={(r) => ({ onClick: () => setSelected(r.vehicle), style: { cursor: "pointer", background: r.vehicle === selected ? "#eef2ff" : undefined } })}
        columns={[
          { title: tr(L.vehicle, lang), dataIndex: "registration_no" },
          { title: tr(L.route, lang), key: "r", render: (_, r) => `${r.route} ${r.route_name}` },
          { title: tr(L.driver, lang), key: "d", render: (_, r) => `${r.driver} ${r.driver_phone}`, responsive: ["md"] },
          { title: tr(L.riders, lang), key: "o", render: (_, r) => `${r.riders} / ${r.capacity}` },
          { title: tr(L.speed, lang), dataIndex: "speed", render: (v) => (v === null ? "—" : `${Number(v)} km/h`) },
          {
            title: tr(L.seen, lang), dataIndex: "age_seconds",
            render: (v: number | null) => v === null ? <Tag>{tr(L.noGps, lang)}</Tag>
              : <Tag color={v < 60 ? "green" : v < 300 ? "blue" : "default"}>{age(v, lang)}{v >= 300 ? ` · ${tr(L.stale, lang)}` : ""}</Tag>,
          },
        ]} />
    </Space>
  );
}

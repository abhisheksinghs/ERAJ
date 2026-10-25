"use client";

import { DeleteOutlined, PlusOutlined } from "@ant-design/icons";
import { Button, Popconfirm, Typography } from "antd";

/** Weekly grid for a section (rows = periods) or a teacher/room (rows = time bands). */
export interface Cell {
  day: number; slot?: number; band?: number; entry: number; section_name: string; subject: string;
  teacher_name: string; room: string | null; substitute_name?: string | null;
}
export interface Grid {
  title: string; kind: "section" | "teacher" | "room"; schedule?: string | null;
  days: { day: number; name: string }[];
  slots?: { slot: number; number: number; label: string; start: string; end: string; is_break: boolean; days: number[] }[];
  bands?: { band: number; start: string; end: string; label: string }[];
  cells: Cell[];
}

const hhmm = (t: string) => t.slice(0, 5);

export function TimetableGrid({ grid, onAdd, onRemove }: {
  grid: Grid;
  onAdd?: (day: number, slot: number) => void;
  onRemove?: (entry: number) => void;
}) {
  const rows = grid.kind === "section"
    ? (grid.slots ?? []).map((s) => ({ key: `s${s.slot}`, id: s.slot, label: s.label, start: s.start, end: s.end, is_break: s.is_break, days: s.days }))
    : (grid.bands ?? []).map((b) => ({ key: `b${b.band}`, id: b.band, label: b.label, start: b.start, end: b.end, is_break: false, days: grid.days.map((d) => d.day) }));
  const find = (day: number, id: number) =>
    grid.cells.find((c) => c.day === day && (grid.kind === "section" ? c.slot === id : c.band === id));

  return (
    <div style={{ overflowX: "auto" }}>
      <table className="tt-grid" style={{ width: "100%", borderCollapse: "collapse", minWidth: 760 }}>
        <thead>
          <tr>
            <th style={th}>Period</th>
            {grid.days.map((d) => <th key={d.day} style={th}>{d.name}</th>)}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.key}>
              <td style={{ ...td, background: "#f1f3f8", width: 120 }}>
                <b>{r.label}</b><br /><Typography.Text type="secondary" style={{ fontSize: 12 }}>{hhmm(r.start)}–{hhmm(r.end)}</Typography.Text>
              </td>
              {r.is_break ? (
                <td style={{ ...td, background: "#eef0f5", fontStyle: "italic", color: "#5b6475" }} colSpan={grid.days.length}>{r.label}</td>
              ) : grid.days.map((d) => {
                if (!r.days.includes(d.day)) return <td key={d.day} style={{ ...td, background: "#f7f8fb" }} />;
                const c = find(d.day, r.id);
                return (
                  <td key={d.day} style={td} data-cell={`${d.day}-${r.id}`}>
                    {c ? (
                      <div style={{ position: "relative" }}>
                        <div style={{ fontWeight: 600 }}>{c.subject}</div>
                        <div style={{ fontSize: 12, color: "#5b6475" }}>
                          {grid.kind === "section" ? c.teacher_name : c.section_name}{c.room && grid.kind !== "room" ? ` · ${c.room}` : ""}
                          {grid.kind === "room" ? ` · ${c.teacher_name}` : ""}
                        </div>
                        {c.substitute_name && <div style={{ fontSize: 12, color: "#b42318", fontWeight: 600 }}>→ {c.substitute_name}</div>}
                        {onRemove && (
                          <Popconfirm title="Remove this period?" onConfirm={() => onRemove(c.entry)}>
                            <Button size="small" type="text" danger icon={<DeleteOutlined />} aria-label="remove period"
                              style={{ position: "absolute", top: -4, right: -4 }} />
                          </Popconfirm>
                        )}
                      </div>
                    ) : onAdd ? (
                      <Button size="small" type="dashed" icon={<PlusOutlined />} onClick={() => onAdd(d.day, r.id)} aria-label={`add ${d.name} ${r.label}`} />
                    ) : null}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

const th: React.CSSProperties = { background: "#1e2761", color: "#fff", padding: "6px 8px", border: "1px solid #c9cedb", textAlign: "left", fontWeight: 600 };
const td: React.CSSProperties = { border: "1px solid #dfe3ec", padding: "6px 8px", verticalAlign: "top", minWidth: 110 };

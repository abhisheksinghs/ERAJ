"use client";

import { DownloadOutlined } from "@ant-design/icons";
import { Button, Card, InputNumber, Result, Select, Space, Typography } from "antd";
import dayjs from "dayjs";
import { useState } from "react";

import { UI } from "@/lib/i18n";
import { API } from "@/lib/refine/dataProvider";
import { useSession } from "@/lib/refine/session";
import { tr, type T } from "@/lib/resources";

/** Year-level payroll reports as Excel: statutory summary, 24Q quarterly data, Form 16 data, year to date. */
const t = (en: string, hi: string): T => ({ en, hi });
const L = {
  title: t("Payroll reports", "वेतन रिपोर्ट"), fy: t("Financial year starting April", "वित्तीय वर्ष (अप्रैल से)"),
  statutory: t("PF, NPS, ESI, PT and TDS by month", "माहवार पीएफ़, एनपीएस, ईएसआई, पीटी एवं टीडीएस"),
  q: t("TDS return data (Form 24Q)", "टीडीएस रिटर्न डेटा (फ़ॉर्म 24Q)"), quarter: t("Quarter", "तिमाही"),
  f16: t("Form 16 data (whole year)", "फ़ॉर्म 16 डेटा (पूरा वर्ष)"), ytd: t("Year-to-date earnings per staff", "कर्मचारीवार वर्ष-अब-तक आय"),
  note: t("Monthly files (bank sheet, ECR, ESIC, PT register, payslips) are on each month's row under Monthly payroll.",
    "मासिक फ़ाइलें (बैंक शीट, ईसीआर, ईएसआईसी, पीटी रजिस्टर, पर्चियाँ) मासिक वेतन की हर पंक्ति पर हैं।"),
};

export default function PayrollReports() {
  const { lang, can, allBranches } = useSession();
  const today = dayjs();
  const [fy, setFy] = useState<number>(today.month() >= 3 ? today.year() : today.year() - 1);
  const [quarter, setQuarter] = useState<number>(1);
  if (!can("payroll.report.view")) return <Result status="403" title={tr(UI.noAccess, lang)} />;
  if (allBranches) return <Result status="info" title={tr(UI.readOnlyAll, lang)} />;
  const xl = (path: string) => `${API}/payroll/reports/${path}${path.includes("?") ? "&" : "?"}fy=${fy}&format=xlsx`;

  return (
    <Space direction="vertical" size="middle" style={{ width: "100%", padding: 8, maxWidth: 720 }}>
      <Typography.Title level={3} style={{ margin: 0 }}>{tr(L.title, lang)}</Typography.Title>
      <Space>
        <Typography.Text>{tr(L.fy, lang)}</Typography.Text>
        <InputNumber value={fy} min={2000} max={2100} onChange={(v) => v && setFy(v)} aria-label="fy" />
        <Typography.Text type="secondary">{fy}-{String(fy + 1).slice(2)}</Typography.Text>
      </Space>
      <Card size="small"><Space style={{ justifyContent: "space-between", width: "100%" }}>{tr(L.statutory, lang)}
        <Button icon={<DownloadOutlined />} href={xl("statutory")}>Excel</Button></Space></Card>
      <Card size="small"><Space style={{ justifyContent: "space-between", width: "100%" }} wrap>{tr(L.q, lang)}
        <Space><Select value={quarter} onChange={setQuarter} aria-label={tr(L.quarter, lang)}
          options={[1, 2, 3, 4].map((q) => ({ value: q, label: `Q${q}` }))} />
          <Button icon={<DownloadOutlined />} href={xl(`tds-24q?quarter=${quarter}`)}>Excel</Button></Space></Space></Card>
      <Card size="small"><Space style={{ justifyContent: "space-between", width: "100%" }}>{tr(L.f16, lang)}
        <Button icon={<DownloadOutlined />} href={xl("form16")}>Excel</Button></Space></Card>
      <Card size="small"><Space style={{ justifyContent: "space-between", width: "100%" }}>{tr(L.ytd, lang)}
        <Button icon={<DownloadOutlined />} href={xl("ytd")}>Excel</Button></Space></Card>
      <Typography.Text type="secondary">{tr(L.note, lang)}</Typography.Text>
    </Space>
  );
}

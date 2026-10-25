"use client";

import { LogoutOutlined } from "@ant-design/icons";
import { Button, Layout, Segmented, Select, Space, Typography } from "antd";

import { UI } from "@/lib/i18n";
import { useSession } from "@/lib/refine/session";
import { tr } from "@/lib/resources";

export function StaffHeader() {
  const { me, branch, allBranches, lang, setBranch, setLang } = useSession();
  if (!me) return null;

  const options = [
    ...me.branches.map((b) => ({ value: String(b.id), label: lang === "hi" && b.name_hi ? b.name_hi : b.name })),
    ...(me.group_admin && me.branches.length > 1 ? [{ value: "all", label: tr(UI.allBranches, lang) }] : []),
  ];

  return (
    <Layout.Header
      style={{
        background: "#fff",
        display: "flex",
        alignItems: "center",
        justifyContent: "flex-end",
        gap: 16,
        padding: "0 16px",
        borderBottom: "1px solid #eef0f4",
        height: 56,
      }}
    >
      <Space size="middle">
        <Select
          aria-label={tr(UI.branch, lang)}
          style={{ minWidth: 200 }}
          value={allBranches ? "all" : branch ? String(branch.id) : undefined}
          options={options}
          onChange={(v) => setBranch(v === "all" ? "all" : Number(v))}
          disabled={options.length < 2}
        />
        <Segmented
          aria-label={tr(UI.language, lang)}
          value={lang}
          onChange={(v) => setLang(v as "en" | "hi")}
          options={[
            { value: "en", label: "EN" },
            { value: "hi", label: "हिं" },
          ]}
        />
        <Typography.Text type="secondary" style={{ maxWidth: 200 }} ellipsis className="hide-narrow">
          {me.first_name ? `${me.first_name} ${me.last_name}`.trim() : me.email}
        </Typography.Text>
        <form action="/logout" method="post" style={{ margin: 0 }}>
          <Button htmlType="submit" icon={<LogoutOutlined />}>
            {tr(UI.signOut, lang)}
          </Button>
        </form>
      </Space>
    </Layout.Header>
  );
}

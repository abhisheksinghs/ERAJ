"use client";

import { Card, Col, Row, Space, Tag, Typography } from "antd";
import Link from "next/link";

import { UI } from "@/lib/i18n";
import { useSession } from "@/lib/refine/session";
import { MODULES, RESOURCES, ROLE, tr } from "@/lib/resources";

export default function Dashboard() {
  const { me, branch, allBranches, lang, can } = useSession();
  const visible = RESOURCES.filter((r) => can(`${r.perm}.view`));
  const modules = MODULES.filter((m) => visible.some((r) => r.module === m.key));

  return (
    <Space direction="vertical" size="large" style={{ width: "100%", padding: 8 }}>
      <div>
        <Typography.Title level={3} style={{ marginBottom: 4 }}>
          {tr(UI.welcome, lang)}
          {me?.first_name ? `, ${me.first_name}` : ""}
        </Typography.Title>
        <Space wrap>
          <Typography.Text type="secondary">{tr(UI.branch, lang)}:</Typography.Text>
          <Tag color="blue">{allBranches ? tr(UI.allBranches, lang) : branch?.name}</Tag>
          {branch?.roles.map((r) => (
            <Tag key={r}>{tr(ROLE.find((o) => o.value === r)?.label ?? { en: r, hi: r }, lang)}</Tag>
          ))}
        </Space>
      </div>
      <Row gutter={[16, 16]}>
        {modules.map((m) => (
          <Col key={m.key} xs={24} sm={12} lg={8}>
            <Card title={tr(m.label, lang)} size="small">
              <Space direction="vertical">
                {visible
                  .filter((r) => r.module === m.key)
                  .map((r) => (
                    <Link key={r.name} href={`/${r.name}`}>
                      {tr(r.label, lang)}
                    </Link>
                  ))}
              </Space>
            </Card>
          </Col>
        ))}
      </Row>
    </Space>
  );
}

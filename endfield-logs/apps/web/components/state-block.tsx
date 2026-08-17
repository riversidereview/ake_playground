type StateBlockProps = {
  title: string;
  description: string;
};

export function StateBlock({ title, description }: StateBlockProps) {
  return (
    <section className="panel panel-muted" style={{ display: "grid", gap: 10, maxWidth: 760 }}>
      <div className="eyebrow">页面状态</div>
      <div>
        <h2 style={{ margin: "0 0 8px" }}>{title}</h2>
        <p className="muted" style={{ margin: 0 }}>
          {description}
        </p>
      </div>
    </section>
  );
}

interface SectorExposurePanelProps {
  exposure: Record<string, number>;
}

export function SectorExposurePanel({ exposure }: SectorExposurePanelProps) {
  const sectors = Object.entries(exposure)
    .sort(([, left], [, right]) => right - left)
    .slice(0, 6);

  const hasConcentrationRisk = sectors.some(([, weight]) => weight >= 35);

  return (
    <section className="rounded-[1.5rem] border border-border bg-card/80 p-5 shadow-lg shadow-black/10 ring-soft">
      <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
        <div>
          <h2 className="text-lg font-semibold text-foreground">Sector exposure</h2>
          <p className="text-sm text-muted-foreground">
            Rychlý check, jestli portfolio neutíká do jedné kapsy trhu.
          </p>
        </div>
        {hasConcentrationRisk ? (
          <div className="rounded-full border border-warning/30 bg-warning/10 px-3 py-1 text-xs font-medium text-yellow-100">
            Nad 35 % v jednom sektoru
          </div>
        ) : null}
      </div>

      {sectors.length ? (
        <div className="mt-5 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {sectors.map(([sector, weight]) => (
            <div
              key={sector}
              className="rounded-2xl border border-border bg-white/4 px-4 py-3"
            >
              <div className="flex items-center justify-between gap-3">
                <span className="text-sm text-foreground">{sector || 'Unknown'}</span>
                <span className="font-mono-price text-sm text-foreground">
                  {weight.toFixed(1)}%
                </span>
              </div>
              <div className="mt-3 h-2 rounded-full bg-white/6">
                <div
                  className="h-full rounded-full bg-primary"
                  style={{ width: `${Math.max(4, Math.min(weight, 100))}%` }}
                />
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="mt-5 rounded-2xl border border-dashed border-border px-4 py-5 text-sm text-muted-foreground">
          Zatím nemáme dost dat pro sector breakdown.
        </div>
      )}
    </section>
  );
}

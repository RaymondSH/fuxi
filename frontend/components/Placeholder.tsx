export default function Placeholder({ title }: { title: string }) {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-3 text-center">
      <div className="font-serif text-2xl font-semibold text-ink">{title}</div>
      <div className="text-sm text-muted">该页面即将实现</div>
    </div>
  );
}

import Link from "next/link";

export default function NotFound() {
  return (
    <main className="grid flex-1 place-items-center p-8 text-center">
      <div className="space-y-2">
        <h1 className="text-2xl font-semibold">Area not found</h1>
        <p className="text-muted-foreground">This place is not in the fire record.</p>
        <Link href="/" className="text-sm underline">
          Back to the map
        </Link>
      </div>
    </main>
  );
}

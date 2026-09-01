import coverage
cov = coverage.Coverage(data_file=".coverage")
cov.load()
data = cov.get_data()
files = [f for f in data.measured_files() if "api" in f.replace("\\", "/").lstrip("/") and "tests" not in f]
print(f"measured api files: {len(files)}")
total_stmts = total_miss = 0
low = []
for f in files:
    res = cov.analysis2(f)
    fn, exe, mis, exl = res[0], res[1], res[2], res[3]
    s = len(exe)
    m = len(mis)
    total_stmts += s
    total_miss += m
    if s > 0:
        pct = 100 * (s - m) / s
        if pct < 80 and s > 20:
            low.append((f.replace("\\", "/"), s, m, pct))
if total_stmts:
    print(f"TOTAL stmts={total_stmts} miss={total_miss} cov={100*(total_stmts-total_miss)/total_stmts:.1f}%")
print("\n--- low coverage (<80%, stmts>20) ---")
for f, s, m, p in sorted(low, key=lambda x: x[3]):
    print(f"{f:50s} stmts={s:4d} miss={m:4d} cov={p:5.1f}%")

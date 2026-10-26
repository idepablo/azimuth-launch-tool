"""Name any vehicle that launched but is not in the classification seed.

The dbt relationship test only warns with a count. This lists the vehicles
on the run page so the seed review knows exactly what to add. Until a
vehicle has a seed row its launches are scoped 'unclassified' and stay out
of the orbital marts. Never fails the run: it is a to-do, not an error.
"""
import os

from load_to_bronze import get_connection


def annotate(level, message):
    if os.environ.get("GITHUB_ACTIONS"):
        print(f"::{level} title=New vehicles::{message}")
    else:
        print(message)


def main():
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT vehicle_key, vehicle_full_name, launch_count,
                       cast(first_launch_at AS date)
                FROM azimuth.gold.dim_vehicle
                WHERE vehicle_class = 'unclassified'
                ORDER BY first_launch_at
            """)
            rows = cur.fetchall()

    if not rows:
        annotate("notice", "Every launched vehicle is in the classification seed.")
        return
    listed = "; ".join(f"{r[1]} (config {r[0]}, {r[2]} launches, first {r[3]})" for r in rows)
    annotate("warning", f"{len(rows)} vehicle(s) need a row in seeds/vehicle_classification.csv: {listed}")


if __name__ == "__main__":
    main()

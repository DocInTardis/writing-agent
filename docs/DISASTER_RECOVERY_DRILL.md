# Multi-region DR Drill

Run periodic backup/restore drill:

```bash
python scripts/disaster_recovery_drill.py --primary .data
```

Artifacts:

- `.data/out/disaster_recovery_drill.json`
- `.data/dr/region-a`
- `.data/dr/region-b`

The drill validates backup copy and cross-region restore paths.

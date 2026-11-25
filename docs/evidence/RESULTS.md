| Model | Dataset | Items | Accuracy (95% CI) | Consistency | Perturbed acc. | Grounded | Stuck |
|---|---|---:|---|---:|---:|---:|---:|
| Pixel oracle (classical CV, integrity check) | prism-core | 1747 | **100.0%** (99.8%-100.0%) | 100.0% | 100.0% | 100.0% | 0.0% |
| Anthropic Haiku 5.5 | prism-core | 443 | **96.6%** (94.5%-97.9%) | 98.3% | 96.7% | 88.3% | 5.0% |
| Anthropic Opus 5.5 | prism-core | 1747 | **95.2%** (94.1%-96.1%) | 94.5% | 96.4% | 90.6% | 2.6% |
| Blind prior (majority answer) | prism-core | 1747 | **25.0%** (23.0%-27.1%) | 88.2% | 27.0% | 0.0% | 90.6% |
| Blind random guess | prism-core | 1747 | **18.7%** (16.9%-20.6%) | 19.8% | 19.9% | 4.3% | 11.6% |

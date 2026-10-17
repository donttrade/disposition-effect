# Licensing for `partner/`

## Which licence applies

| Version | Licence |
|---|---|
| `partner-v1` (commit `2ff165c`, 13 October 2026) and earlier | MIT, as the repository root `LICENSE`. That grant stands and is not withdrawn. |
| Every later version | [PolyForm Noncommercial 1.0.0](LICENSE.md), with the notice in [`NOTICE`](NOTICE) |

## In plain words

**Free:** traders running it on their own records; students, researchers, schools, charities, journalists and government bodies; anyone reading or auditing the code.

**Needs a commercial licence:** a business using it for its business — for example, a prop firm or broker running it on its own client records, or publishing, quoting or marketing any figure it produced. A commercial licence comes with every donttrade engagement. Contact: donttrade.research@gmail.com.

## Additional permission: evaluation

On top of the PolyForm terms, any organisation may run any version of this software **on synthetic or test data** (for example the file `make_fixture.py` writes) for up to 32 days, to decide whether to commission an engagement. This permission does not cover real client records, and it does not cover publishing or quoting anything the software prints.

## The files in this folder

| File | Licence |
|---|---|
| `partner_disposition.py` (v2, 17 October 2026, per-bound intervals, SHA-256 `c096e375e4e67c9f9c0164f4863b292eea567da3f71132ebba44caf7237388dc`) | PolyForm Noncommercial 1.0.0, as above |
| `make_fixture.py` (the synthetic test-file generator) | PolyForm Noncommercial 1.0.0, as above |
| `README.md`, `EXPORT-GUIDE.md`, this file | PolyForm Noncommercial 1.0.0, as above |
| `LICENSE.md` | the PolyForm Noncommercial 1.0.0 terms, unchanged |
| `NOTICE` | the required notice |

A file that is unchanged since `partner-v1` is also available under MIT from that commit; the MIT grant is not
withdrawn.

## The Open Behavioural Measurement Spec (OBMS) is licensed separately

The OBMS draft, which defines what this script measures and the suite that checks it, is a separate folder with
its own licence file (`LICENSE` in the spec folder):
- **Specification text** (`SPEC.md`, `README.md`, `CHANGELOG.md` there): Creative Commons Attribution 4.0
  International (CC BY 4.0).
- **Conformance suite** (everything under `test-suite/` there, including the oracle): MIT.

This script is one implementation of that spec. It is not part of the spec, and the spec's licences do not
cover it. The spec's licences do not change this folder's licence, and this folder's licence does not restrict
the spec: anyone may implement the spec, commercially or not, without using this script.

## Name

No one may describe a figure as measured, verified, certified, audited or produced by donttrade, or imply that donttrade endorses a firm, except under a signed engagement and in the wording that engagement allows.

## Text, charts and numbers

Study write-ups and charts on the website are licensed CC BY-NC 4.0. The numbers in them are facts: quote them freely, with a link. A figure about one public panel says nothing about any firm's traders.

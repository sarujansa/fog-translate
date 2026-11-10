# Security / Sicherheit

**English:** Please do not report security problems in a public issue. Use
[Report a vulnerability](https://github.com/senisinx/fog-translate/security/advisories/new) (private on GitHub)
and describe what is affected, how to reproduce it and which version you use (window title or
release). Only the latest release is supported. You will get an answer as soon as possible;
please wait for the fix before publishing details.

**Deutsch:** Sicherheitsprobleme bitte nicht als öffentliches Issue melden, sondern über
[Report a vulnerability](https://github.com/senisinx/fog-translate/security/advisories/new) (privat auf GitHub):
was betroffen ist, wie man es nachstellt und welche Version (Fenstertitel bzw. Release). Unterstützt wird
nur das neueste Release. Bitte Details erst nach dem Fix veröffentlichen.

## Check a download / Download prüfen

Every setup of Fog Translate is built by GitHub Actions and carries a build-provenance attestation (releases from November 2026 on). With the
GitHub CLI: / Jedes Setup von Fog Translate baut GitHub Actions und versieht es mit einem Herkunftsnachweis (Releases ab November 2026).
Mit der GitHub-CLI:

```
gh attestation verify <Setup>.exe -R senisinx/fog-translate
```

The release also lists the SHA-256 of the setup. / Das Release nennt zusätzlich die SHA-256 des Setups.

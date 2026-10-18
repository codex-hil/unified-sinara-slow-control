# Licensing and source attribution

Original host tools, firmware cores and project documentation: MIT (LICENSE).
Existing file notices take precedence; this is not a relicensing of upstream.

- ESPHome C/C++ runtime, vendored SPI/I2C, their adapters and Sinara ESPHome
  C++ components: GPLv3. ESPHome Python integration: MIT. Full upstream text:
  integrations/esphome/UPSTREAM_LICENSE.txt. Local changes and original hashes:
  integrations/esphome/provenance.json and upstream-adapter.patch.
- MODULIQ addrspi/addrspi2: unchanged pinned source; original CODEOWNERS retained.
  See integrations/esphome/ADDRESSED_SPI_NOTICE.md, MODULIQ-ESPHOME-LICENSE
  and evidence/addressed-spi-upstream/manifest.json.
- ARTIQ driver reference logic: LGPLv3; preserve notices for any adaptations.
  License and incorporated GPL text are under licenses/artiq-*.
  Device register definitions/algorithms and slow-control separation are
  described in docs/URUKUL.md, SAMPLER.md and ZOTINO.md.
- Migen, MiSoC and LiteX code/excerpts: original BSD notices retained under
  licenses/. Reference revisions: evidence/source-commits.json.
- openFPGALoader audit excerpts evidence/ofl-*.cpp retain their copyright
  headers and GPLv3 terms. The GPL text is in licenses/artiq-LICENSE.GPL-3;
  exact source revisions and links are in evidence/flash-source-audit.json.

Downloaded STM source snapshots and hardware schematic extracts are not
redistributed here. Their original upstream license status is not overridden
by this repository. Fetch original repositories/PDFs using
`python3 tools/fetch_references.py`; commit and PDF hashes are recorded in
source-commits.json and pdf-sources.json. Generated FPGA images and caches
are excluded; reports identify the local artifacts used during testing.

Publishing this project does not imply upstream authors tested or endorse it.
All board-level validation statuses remain as documented in STATUS.md.

SCF5 portable client/HAL headers and compile probes: MIT, independent of the
ESPHome runtime adapter (GPLv3). STM32 HAL/CMSIS headers are fetched only into
ignored work storage; their pinned source manifest is evidence/scf5-stm32-sdk.json.
They are not relicensed or redistributed by this repository.

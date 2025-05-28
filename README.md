# Avancerad Elbilsladdning för Home Assistant

Detta är en anpassad integration (custom component) för Home Assistant som möjliggör avancerad styrning av elbilsladdning, primärt med fokus på Easee-laddboxar.

## Funktioner
* **Pris/Tid-styrd laddning**: Ladda när elpriset är lågt och inom definierade tidsscheman.
* **Solenergiladdning**: Ladda med överskott från egna solpaneler.
* **SoC-gräns**: Ställ in en maximal laddningsnivå för bilen.
* **Dynamisk kontroll**: Anpassar laddningen baserat på flera faktorer i realtid.
* **Sessionsdata**: Sensorer för energi och kostnad per laddningssession.
* **Anpassningsbara entiteter**: Skapar switchar och nummerinmatningar för enkel kontroll via Home Assistant UI.
* **Debug-läge**: Möjlighet att aktivera detaljerad loggning för felsökning.

## Installation
1.  Se till att du har [HACS (Home Assistant Community Store)](https://hacs.xyz/) installerat (rekommenderat), eller installera manuellt.
2.  **Via HACS (Rekommenderat):**
    * Sök efter "Avancerad Elbilsladdning" (eller det namn integrationen får i HACS) under Integrationer.
    * Installera integrationen.
3.  **Manuell Installation:**
    * Ladda ner den senaste versionen från [GitHub-repot](https://github.com/AlleHj/home-assistant-smart_ev_charging).
    * Kopiera innehållet i `custom_components/smart_ev_charging/` till din Home Assistant-konfigurationsmapp under `<HA_config_mapp>/custom_components/smart_ev_charging/`.
4.  Starta om Home Assistant.
5.  Gå till "Inställningar" -> "Enheter & Tjänster" -> "Lägg till Integration" och sök efter "Avancerad Elbilsladdning".
6.  Följ konfigurationsguiden. Detaljerad information om varje parameter finns i [HELP.md](HELP.md).

## Konfiguration
All konfiguration sker via Home Assistants användargränssnitt, både vid initial installation och senare via "Alternativ" på integrationskortet.
För en detaljerad genomgång av alla konfigurationsalternativ, se [HELP.md](HELP.md).

## Versionshistorik

### Version 0.1.5 (2025-05-28)
* **Kodförbättring**: Ytterligare åtgärder för Pylint/linter-varningar i `coordinator.py`:
    * Korrigerat logganrop med komplexa f-strängar till att använda korrekta format specifiers och argument (lazy logging).
    * Justerat `if/elif`-strukturer i `_get_surcharge_in_kr_kwh` och `_get_power_value` för att tydligare hantera returvärden i `else`-block och undvika "Consider moving this statement to an `else` block"-varningar.
* **Dokumentation**: Uppdaterade filversionskommentar i `coordinator.py` och `manifest.json`.

### Version 0.1.4 (2025-05-28)
* **Kodförbättring**:
    * Åtgärdat Pylint/linter-varningar i `coordinator.py`:
        * Ändrat f-strängar till lazy %-formatering i logganrop (`_LOGGER.debug`, `_LOGGER.info`, etc.).
        * Korrigerat "Unnecessary `elif` after `return` statement" genom att byta till `if`.
        * Förbättrat multipla jämförelser genom att använda `in` (t.ex. `unit in (UnitOfPower.KILO_WATT, "kw")`).
* **Dokumentation**: Uppdaterade filversionskommentar i `coordinator.py` och `manifest.json`.

### Version 0.1.3 (2025-05-28)
* **Felrättning**: Korrigerade ett `NameError` i `coordinator.py` där `asyncio` anropades utan att först ha importerats. Lade till `import asyncio`.
* **Dokumentation**: Uppdaterade filversionskommentar i `coordinator.py` och `manifest.json`.

### Version 0.1.2 (2025-05-28)
* **Ny funktion**: Lade till konfigurationsalternativ (kryssruta) för att aktivera/avaktivera debug-loggning direkt från UI (både vid initial setup och i OptionsFlow). Loggningsnivån för integrationen (`custom_components.smart_ev_charging`) sätts nu dynamiskt.
* **Dokumentation**:
    * Skapade en omfattande `HELP.md`-fil som beskriver integrationens syfte, funktionalitet, konfigurationsparametrar och felsökning.
    * Länk till `HELP.md` är nu tillgänglig i `manifest.json` under `documentation`.
    * Förbättrade beskrivningar för vissa valfria fält direkt i konfigurationsdialogen (`config_flow.py`) för ökad tydlighet.
    * Uppdaterade `README.md` med installationsinstruktioner och denna versionshistorik.
* **Kodförbättringar**:
    * Standardiserade filversionskommentarer i alla Python-filer till formatet `# File version: ÅÅÅÅ-MM-DD <MANIFEST_VERSION>`.
    * Uppdaterade `manifest.json` till version `0.1.2` och korrigerade `codeowners` till `@AllehJ`.
    * Förtydligade logger-användning i `__init__.py` och `coordinator.py` för att bättre respektera den nya debug-inställningen.
    * Förbättrad hantering av initial fördröjning i `coordinator.py` (`_async_first_refresh`) för att ge andra entiteter tid att starta.
    * Förbättrad loggning av otillgängliga/ej hittade entiteter i `coordinator.py` för att minska loggspam.
    * Säkerställde att listeners tas bort korrekt vid `async_unload_entry` och vid Home Assistant shutdown.
    * Mindre justeringar i `config_flow.py` för att bättre hantera default-värden och återpopulering av formulär vid fel.

### Version 0.1.1 (Basversion från dokument)
* Initial version baserad på den funktionalitet som beskrivs i "Utveckling av Custom Component Avancerad Elbilsladdning för Home Assistant.docx" daterat 2025-05-23 och de ursprungliga kodfilerna.

## Bidra
Om du vill bidra till utvecklingen, vänligen skapa ett "Issue" eller en "Pull Request" på [GitHub-repot](https://github.com/AlleHj/home-assistant-smart_ev_charging).

## Licens
Detta projekt är licensierat under [Apache 2.0-licensen](LICENSE) (eller annan relevant licens om specificerat i repot).
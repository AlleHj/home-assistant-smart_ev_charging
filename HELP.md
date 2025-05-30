# Avancerad Elbilsladdning - Användarmanual

Detta dokument beskriver hur du installerar, konfigurerar och använder den anpassade integrationen "Avancerad Elbilsladdning" för Home Assistant. Målet med integrationen är att ge en flexibel och intelligent styrning av din elbilsladdning.

## Innehållsförteckning
- [Introduktion](#introduktion)
- [Funktioner](#funktioner)
- [Systemkrav](#systemkrav)
- [Installation](#installation)
- [Konfiguration](#konfiguration)
  - [Obligatoriska fält](#obligatoriska-fält)
  - [Valfria fält och deras betydelse](#valfria-fält-och-deras-betydelse)
  - [Exempel på sensorer](#exempel-på-sensorer)
- [Entiteter som skapas av integrationen](#entiteter-som-skapas-av-integrationen)
- [Hur styrningslogiken fungerar](#hur-styrningslogiken-fungerar)
  - [Pris/Tid-styrd laddning](#pristid-styrd-laddning)
  - [Solenergiladdning](#solenergiladdning)
  - [SoC-gräns (State of Charge)](#soc-gräns-state-of-charge)
  - [Prioritering mellan lägen](#prioritering-mellan-lägen)
- [Felsökning](#felsökning)
- [Testfall](#testfall)
- [Bidra](#bidra)
- [Licens](#licens)

## Introduktion
Avancerad Elbilsladdning är en integration designad för att optimera laddningen av din elbil genom att ta hänsyn till faktorer som elpris, tillgänglig solenergi och bilens aktuella laddningsnivå. Den är primärt utvecklad med Easee-laddboxar i åtanke men kan vara anpassningsbar.

## Funktioner
Se [README.md](README.md) för en komplett lista över funktioner.

## Systemkrav
För att använda denna integration behöver du:
* En fungerande Home Assistant-installation.
* Easee EV Charger-integrationen korrekt installerad och konfigurerad (om du använder en Easee-laddbox).
* Externa sensorer och hjälpare i Home Assistant som tillhandahåller nödvändig data (se [Konfiguration](#konfiguration)).

## Installation
Installationsinstruktioner finns i [README.md](README.md).

## Konfiguration
All konfiguration sker via Home Assistants användargränssnitt när du lägger till integrationen, och kan senare justeras via "Alternativ" på integrationskortet.

### Obligatoriska fält
Dessa måste fyllas i för att integrationen ska kunna starta:
* **Easee Laddarenhet (`charger_device_id`):** Välj den Easee-laddarenhet du vill styra.
* **Statussensor för Laddaren (`status_sensor_id`):** Sensorn som rapporterar laddarens aktuella status (t.ex. `sensor.min_laddbox_status`).
* **Huvudströmbrytare för Laddboxen (`charger_enabled_switch_id`):** Switchen som helt aktiverar/deaktiverar strömmen till laddboxen (t.ex. `switch.min_laddbox_aktiverad`).
* **Elprissensor (Spotpris) (`price_sensor_id`):** Sensorn som rapporterar aktuellt el-spotpris (t.ex. från Nordpool).

### Valfria fält och deras betydelse
En komplett lista och beskrivning av alla konfigurationsparametrar, både obligatoriska och valfria (som t.ex. SoC-sensor, solproduktion, tidsscheman), finns i UI:t när du konfigurerar integrationen och detaljeras ytterligare i detta dokument under relevanta funktionsbeskrivningar.

*(Här skulle en mer detaljerad genomgång av varje konfigurationsalternativ kunna läggas in, liknande det som finns i `Utveckling av Custom Component Avancerad Elbilsladdning för Home Assistant.docx`)*

## Entiteter som skapas av integrationen
Integrationen skapar automatiskt följande entiteter för att du ska kunna interagera med och övervaka de smarta laddningsfunktionerna:
* **Switch (`..._smart_charging_enabled`):** "Avancerad Elbilsladdning Smart Laddning Aktiv" - Aktiverar/avaktiverar den pris/tid-styrda smartladdningen.
* **Switch (`..._solar_surplus_charging_enabled`):** "Avancerad Elbilsladdning Aktivera Solenergiladdning" - Aktiverar/avaktiverar laddning med solenergiöverskott.
* **Nummer (`..._max_charging_price`):** "Avancerad Elbilsladdning Max Elpris" - Ställer in det maximala spotpriset (kr/kWh) för Pris/Tid-laddning.
* **Nummer (`..._solar_charging_buffer`):** "Avancerad Elbilsladdning Solenergi Buffer" - Ställer in en effektbuffert (Watt) som reserveras för husets behov innan solenergi används för laddning.
* **Nummer (`..._min_solar_charging_current`):** "Avancerad Elbilsladdning Minsta Laddström Solenergi" - Ställer in den minsta strömstyrka (Ampere) som krävs från solöverskott för att starta/fortsätta solenergiladdning.
* **Sensor (`..._active_control_mode`):** "Avancerad Elbilsladdning Aktivt Styrningsläge" - Visar det faktiska styrningsläget som för närvarande är aktivt och kontrollerar laddningen: "PRIS_TID", "SOLENERGI" eller "AV" (manuell).

## Hur styrningslogiken fungerar
Kärnan i integrationen är `SmartEVChargingCoordinator` som periodiskt utvärderar alla indata och fattar beslut om laddningen ska starta, stoppa eller justeras.

### Pris/Tid-styrd laddning
Om denna funktion är aktiverad (via switchen "...Smart Laddning Aktiv") kommer integrationen att försöka ladda bilen när:
1.  Ett eventuellt konfigurerat tidsschema (`CONF_TIME_SCHEDULE_ENTITY`) är aktivt.
2.  Det aktuella el-spotpriset (`CONF_PRICE_SENSOR`) är lägre än eller lika med det av användaren inställda maxpriset (via nummerentiteten "...Max Elpris").
Laddströmmen sätts då vanligtvis till laddarens maximala hårdvarubegränsning (från `CONF_CHARGER_MAX_CURRENT_LIMIT_SENSOR` eller ett standardvärde).

### Solenergiladdning
Om denna funktion är aktiverad (via switchen "...Aktivera Solenergiladdning") och Pris/Tid-laddning inte är aktiv, försöker integrationen ladda med överskottsenergi från solpaneler. Detta sker när:
1.  Ett eventuellt konfigurerat tidsschema för solenergiladdning (`CONF_SOLAR_SCHEDULE_ENTITY`) är aktivt.
2.  Det finns tillräckligt med solöverskott (Solproduktion - Husförbrukning - Solenergi Buffer) för att driva laddaren med minst den inställda minimiströmmen för solenergiladdning.
3.  Detta överskott har varit stabilt under en viss tid (`SOLAR_SURPLUS_DELAY_SECONDS`) för att undvika korta start/stopp.
Laddströmmen anpassas dynamiskt efter tillgängligt överskott.

### SoC-gräns (State of Charge)
Om en SoC-sensor (`CONF_EV_SOC_SENSOR`) och en övre SoC-gräns (`CONF_TARGET_SOC_LIMIT`) är konfigurerade, kommer all smart laddning (både Pris/Tid och Solenergi) att förhindras eller pausas om bilens aktuella laddningsnivå når eller överskrider denna gräns.

### Prioritering mellan lägen
Styrningslogiken följer en prioriteringsordning:
1.  **SoC-gräns:** Har högst prioritet och kan stoppa all smart laddning.
2.  **Pris/Tid-styrd laddning:** Om SoC tillåter och villkoren för Pris/Tid är uppfyllda, aktiveras detta läge.
3.  **Solenergiladdning:** Om SoC tillåter och Pris/Tid-laddning *inte* är aktivt, kan solenergiladdning aktiveras om dess villkor är uppfyllda.
Om inga smarta lägen är aktiva eller deras villkor uppfylls, går laddningen över till manuell kontroll (eller vad laddarens egna eventuella scheman dikterar).

## Felsökning
*(Här kan vanliga problem och lösningar listas, t.ex. varför laddning inte startar, loggkontroller, etc.)*
* **Debug-loggning:** Kan aktiveras via integrationens alternativ för att få mer detaljerad information i Home Assistant-loggarna.
* **Kontrollera externa sensorer:** Säkerställ att alla sensorer du har konfigurerat (elpris, SoC, effekt etc.) rapporterar korrekta och tillgängliga värden i Home Assistant.
* **Enhets-ID:n för interna entiteter:** Om du behöver felsöka eller använda de av integrationen skapade switcharna/numren i automationer, har de unika ID:n baserade på konfigurationspostens ID och fasta suffix (t.ex. `..._smart_charging_enabled`).

## Testfall
Nedan beskrivs de automatiska tester som har utvecklats för att säkerställa integrationens funktionalitet. Dessa tester körs med `pytest` och testramverket `pytest-homeassistant-custom-component`.

### Fil: `tests/test_init.py`
* **Testfunktion:** `test_load_and_unload_entry`
    * **Syfte:** Verifierar den mest grundläggande livscykeln: att integrationen kan laddas korrekt baserat på en konfiguration och sedan avladdas utan fel.
    * **Scenario/Förutsättningar:** En mockad `ConfigEntry` skapas med de obligatoriska konfigurationsfälten. Externa sensorer (status, huvudenhetens strömbrytare, elpris) får initiala, giltiga tillstånd.
    * **Utförande & Förväntat Resultat:** Integrationen startas via `hass.config_entries.async_setup()`. Kontrollerar att status blir `LOADED` och att en av integrationens entiteter (t.ex. switchen för "Smart Laddning Aktiv") skapats med sitt standardtillstånd (AV). Därefter avladdas integrationen via `hass.config_entries.async_unload()` och status kontrolleras till `NOT_LOADED`.

### Fil: `tests/test_coordinator.py`
* **Testfunktion:** `test_price_time_charging_starts_when_conditions_are_met`
    * **Syfte:** Säkerställer att koordinatorns logik startar Pris/Tid-laddning när alla nödvändiga villkor är uppfyllda.
    * **Scenario/Förutsättningar:** Laddarens status är "redo att ladda", elpriset är under det inställda maxpriset, tidsschemat för Pris/Tid är aktivt, huvudswitchen "Smart Laddning Aktiv" är PÅ, och solenergiladdning är explicit satt till AV för att isolera testet.
    * **Utförande & Förväntat Resultat:** Koordinatorn uppdateras manuellt. Testet förväntar sig att tjänsteanrop görs till Easee-laddaren för att sätta dynamisk ström (`set_dynamic_charger_circuit_current`) och återuppta/starta laddning (`resume_charging`). Koordinatorns `active_control_mode` ska bli `CONTROL_MODE_PRICE_TIME`.

* **Testfunktion:** `test_price_time_charging_does_not_call_set_current_unnecessarily`
    * **Syfte:** Testar optimeringslogiken; att `set_dynamic_charger_circuit_current` *inte* anropas om Pris/Tid-laddning redan pågår och den aktiva dynamiska strömgränsen (från `CONF_CHARGER_DYNAMIC_CURRENT_SENSOR`) redan är densamma som målvärdet.
    * **Scenario/Förutsättningar:** Alla villkor för Pris/Tid-laddning är uppfyllda, laddaren är i status 'charging', och sensorn för den nuvarande dynamiska strömgränsen visar samma värde som koordinatorns målvärde. Solenergiladdning är AV.
    * **Utförande & Förväntat Resultat:** Koordinatorn uppdateras. Inga anrop till `set_dynamic_charger_circuit_current` eller `resume_charging` förväntas.

* **Testfunktion:** `test_charging_stops_when_soc_limit_is_reached`
    * **Syfte:** Kontrollerar att laddningen pausas när bilens batterinivå (SoC) når den konfigurerade övre gränsen.
    * **Scenario/Förutsättningar:** Laddning pågår. En sensor för bilens SoC (`CONF_EV_SOC_SENSOR`) rapporterar ett värde som är lika med eller högre än den inställda SoC-gränsen (`CONF_TARGET_SOC_LIMIT`).
    * **Utförande & Förväntat Resultat:** Koordinatorn uppdateras. Anrop till tjänsten för att pausa laddning (`pause_charging`) förväntas. Ett relevant meddelande ska loggas.

* **Testfunktion:** `test_full_day_price_time_simulation`
    * **Syfte:** En mer omfattande test av Pris/Tid-logiken genom att simulera ett helt dygn, timme för timme, med varierande elpriser och schematillstånd.
    * **Scenario/Förutsättningar:** Ett slumpmässigt maxpris och slumpmässigt aktiva timmar för laddningsschemat genereras, tillsammans med slumpade timvisa spotpriser. Smart-laddningsswitchen är PÅ, solenergiladdning AV.
    * **Utförande & Förväntat Resultat:** För varje timme simuleras elpris och schematillstånd. Koordinatorn körs, och testet verifierar att laddningen startar/stoppar korrekt baserat på om priset är under maxpriset och schemat är aktivt.

### Fil: `tests/test_connection_override.py`
* **Testfunktion:** `test_charger_connection_sequence_and_pause_override`
    * **Syfte:** Verifierar hanteringen av en typisk anslutningssekvens (bil kopplas in) och att integrationen kan återta kontrollen om en pågående laddning (styrd av Pris/Tid) pausas externt.
    * **Scenario/Förutsättningar:** Pris/Tid-laddning är konfigurerad att vara aktiv (lågt pris, ingen schemabegränsning).
    * **Utförande & Förväntat Resultat - Stegvis:**
        1.  **Frånkopplad:** Initial status `disconnected`. Ingen laddningsaktivitet.
        2.  **Anslutning:** Status ändras till `awaiting_start`. Integrationen ska starta laddning (`resume_charging`, `set_dynamic_current`).
        3.  **Laddning pågår:** Status `charging`. Inga onödiga kommandon ska skickas om strömmen är korrekt.
        4.  **Externt pausad:** Status ändras från `charging` till `awaiting_start`. Integrationen ska omedelbart återuppta laddningen (`resume_charging`) eftersom Pris/Tid-villkoren fortfarande är uppfyllda.

### Fil: `tests/test_solar_to_price_time_transition.py`
* **Testfunktion:** `test_solar_to_price_time_transition`
    * **Syfte:** Kontrollerar att Pris/Tid-laddning korrekt prioriteras och tar över från en pågående Solenergiladdning när Pris/Tid-schemat blir aktivt.
    * **Scenario/Förutsättningar:**
        * Kl. 19:00: Solenergiladdning är aktiv (god solproduktion, relevanta switchar PÅ, Pris/Tid-schema är AV). Ström är satt baserat på solöverskott (t.ex. 6A efter trefasberäkning och tillräcklig sol).
        * Kl. 20:00: Pris/Tid-schemat blir aktivt. Elpriset är fortfarande lågt.
    * **Utförande & Förväntat Resultat:**
        * Kl. 19:00: `active_control_mode` är `CONTROL_MODE_SOLAR_SURPLUS`. `set_dynamic_current` har anropats med korrekt solenergi-beräknad ström.
        * Kl. 20:00: `active_control_mode` byter till `CONTROL_MODE_PRICE_TIME`. `set_dynamic_current` anropas igen, nu med maximal hårdvaruström.

### Fil: `tests/test_solar_to_price_time_on_price_drop.py`
* **Testfunktion:** `test_solar_to_price_time_on_price_drop`
    * **Syfte:** Verifierar att Pris/Tid-laddning tar över från Solenergiladdning när elpriset sjunker, vilket gör Pris/Tid aktivt och mer prioriterat, även utan schemaändringar.
    * **Scenario/Förutsättningar:**
        * Initialt: Högt elpris (över maxgräns för Pris/Tid), god solproduktion. Båda laddningstypernas switchar är PÅ. Inga tidsstyrda scheman. Solenergiladdning är aktiv.
        * Senare: Elpriset sjunker under maxgränsen för Pris/Tid.
    * **Utförande & Förväntat Resultat:**
        * Initialt (högt pris): `active_control_mode` är `CONTROL_MODE_SOLAR_SURPLUS`. Dynamisk ström satt baserat på solöverskott (t.ex. 10A efter trefasjustering).
        * Efter prissänkning: `active_control_mode` byter till `CONTROL_MODE_PRICE_TIME`. Dynamisk ström sätts till hårdvarumaximum.

### Fil: `tests/test_config_flow_and_options_persistence.py`
* **Testfunktion:** `test_setup_and_options_modification_flow`
    * **Syfte:** Testar hela konfigurations- och alternativflödet programmatiskt för att säkerställa att data sparas och återläses korrekt genom UI-simulering.
    * **Scenario/Förutsättningar:** Använder mockade entitets-ID:n. En slumpmässig SoC-gräns genereras.
    * **Utförande & Förväntat Resultat - Stegvis:**
        1.  **Initial Setup:** Skapar integrationen via konfigurationsflödet. Fyller i obligatoriska fält, SoC-sensor och SoC-gräns. Valfria fält lämnas initialt tomma (`None`). Verifierar att `ConfigEntry.data` innehåller korrekta värden.
        2.  **Öppna Options (Kontroll 1):** Initierar alternativflödet. Verifierar att flödet startar korrekt (formulär visas), vilket implicit visar att `entry.data` är giltigt.
        3.  **Modifiera Options:** Simulerar att SoC-sensorn tas bort (input `None`), en EV Power-sensor läggs till, och andra valfria fält fylls i. Ändringarna sparas. Verifierar att `ConfigEntry.options` nu innehåller de uppdaterade värdena och att även tidigare `data`-fält nu finns i `options`.
        4.  **Öppna Options (Kontroll 2):** Initierar alternativflödet igen. Verifierar att flödet startar korrekt, vilket implicit visar att `entry.options` är giltigt och används för att bygga formuläret.

## Bidra
Se [README.md](README.md) för information om hur du kan bidra till projektet.

## Licens
Detta projekt är licensierat under Apache 2.0-licensen. Se [LICENSE](../../LICENSE) (eller motsvarande fil i repot) för fullständig licenstext. (Antagande om licens, justera vid behov).
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
Se även `config_flow.py` för en teknisk översikt av alla fält.

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
2.  Det aktuella el-spotpriset (`CONF_PRICE_SENSOR`) plus eventuellt påslag (`CONF_SURCHARGE_HELPER`) är lägre än eller lika med det av användaren inställda maxpriset (via nummerentiteten "...Max Elpris").
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
1.  **SoC-gräns:** Har högst prioritet och kan stoppa/förhindra all smart laddning.
2.  **Pris/Tid-styrd laddning:** Om SoC tillåter och villkoren för Pris/Tid är uppfyllda, aktiveras detta läge.
3.  **Solenergiladdning:** Om SoC tillåter och Pris/Tid-laddning *inte* är aktivt, kan solenergiladdning aktiveras om dess villkor är uppfyllda.
Om inga smarta lägen är aktiva eller deras villkor uppfylls, går laddningen över till manuell kontroll (eller vad laddarens egna eventuella scheman dikterar).

## Felsökning
* **Debug-loggning:** Kan aktiveras via integrationens alternativ (`CONF_DEBUG_LOGGING`) för att få mer detaljerad information i Home Assistant-loggarna (`custom_components.smart_ev_charging`).
* **Kontrollera externa sensorer:** Säkerställ att alla sensorer du har konfigurerat (elpris, SoC, effekt etc.) rapporterar korrekta och tillgängliga värden i Home Assistant.
* **Enhets-ID:n för interna entiteter:** De av integrationen skapade entiteterna (switchar, nummer, sensor) får ID:n baserade på `DEFAULT_NAME` ("Avancerad Elbilsladdning") och deras specifika funktion, t.ex. `switch.avancerad_elbilsladdning_smart_laddning_aktiv`.

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
        * Kl. 19:00: Solenergiladdning är aktiv (god solproduktion, relevanta switchar PÅ, Pris/Tid-schema är AV). Ström är satt baserat på solöverskott.
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
        * Initialt (högt pris): `active_control_mode` är `CONTROL_MODE_SOLAR_SURPLUS`. Dynamisk ström satt baserat på solöverskott.
        * Efter prissänkning: `active_control_mode` byter till `CONTROL_MODE_PRICE_TIME`. Dynamisk ström sätts till hårdvarumaximum.

### Fil: `tests/test_config_flow_and_options_persistence.py`
* **Testfunktion:** `test_setup_and_options_modification_flow`
    * **Syfte:** Testar hela konfigurations- och alternativflödet programmatiskt för att säkerställa att data sparas och återläses korrekt genom UI-simulering.
    * **Scenario/Förutsättningar:** Använder mockade entitets-ID:n. En slumpmässig SoC-gräns genereras.
    * **Utförande & Förväntat Resultat - Stegvis:**
        1.  **Initial Setup:** Skapar integrationen via konfigurationsflödet. Fyller i obligatoriska fält, SoC-sensor och SoC-gräns. Valfria fält lämnas initialt tomma (`None`). Verifierar att `ConfigEntry.data` innehåller korrekta värden.
        2.  **Öppna Options (Kontroll 1):** Initierar alternativflödet. Verifierar att flödet startar korrekt.
        3.  **Modifiera Options:** Simulerar att SoC-sensorn tas bort (input `None`), en EV Power-sensor läggs till, och andra valfria fält fylls i. Ändringarna sparas. Verifierar att `ConfigEntry.options` nu innehåller de uppdaterade värdena.
        4.  **Öppna Options (Kontroll 2):** Initierar alternativflödet igen. Verifierar att flödet startar korrekt, vilket implicit visar att `entry.options` är giltigt.

### Fil: `tests/test_loggning_vid_frånkoppling.py`
* **Testfunktion:** `test_logging_and_state_on_disconnect`
    * **Syfte:** Verifierar att korrekt loggning sker och att sessionsdata återställs när en bil kopplas från under pågående laddning, samt att loggningen inte upprepas vid efterföljande kontroller.
    * **Scenario/Förutsättningar:** En Pris/Tid-laddning simuleras som aktiv. Laddarens status är initialt 'charging'.
    * **Utförande & Förväntat Resultat - Stegvis:**
        1.  **Frånkoppling:** Status ändras till 'disconnected'. Koordinatorn uppdateras. Loggen ska innehålla "Återställer sessionsdata..." exakt en gång. Styrningsläget ska bli "AV". Koordinatorns `session_start_time_utc` ska nollställas.
        2.  **Repeterad kontroll:** Koordinatorn uppdateras igen med status 'disconnected'. Inga nya relevanta varnings- eller infomeddelanden ska loggas.

### Fil: `tests/test_solenergiladdning_livscykel.py`
* **Testfunktion:** `test_solar_charging_full_lifecycle`
    * **Syfte:** Testar hela livscykeln för solenergiladdning, från otillräckligt överskott, genom fördröjning, till start, dynamisk justering av ström och slutligen paus när överskottet försvinner.
    * **Scenario/Förutsättningar:** Integrationen konfigureras för solenergiladdning (relevanta sensorer mockas, switchar och nummer-entiteter sätts). Olika nivåer av solproduktion och husförbrukning simuleras.
    * **Utförande & Förväntat Resultat - Stegvis:**
        1.  **Inget/Otillräckligt överskott:** Ingen laddning startar. Styrningsläge `CONTROL_MODE_MANUAL`.
        2.  **Tillräckligt överskott (inom fördröjning):** Ingen laddning än, men fördröjningstimer (`_solar_surplus_start_time`) initieras.
        3.  **Laddning startar efter fördröjning:** Laddning återupptas, korrekt ström sätts. Styrningsläge `CONTROL_MODE_SOLAR_SURPLUS`.
        4.  **Laddström justeras dynamiskt:** Solproduktionen ändras, laddströmmen anpassas.
        5.  **Laddning pausas:** Solöverskottet försvinner, laddningen pausas. Styrningsläge `CONTROL_MODE_MANUAL`.

### Fil: `tests/test_active_control_mode_sensor.py`
* **Testfunktion:** `test_active_control_mode_sensor_updates`
    * **Syfte:** Verifierar att sensorn `sensor.avancerad_elbilsladdning_aktivt_styrningslage` uppdateras korrekt till `PRIS_TID`, `SOLENERGI` eller `AV` (Manuell) baserat på koordinatorns beslut.
    * **Scenario/Förutsättningar:** Olika förutsättningar skapas för att trigga respektive styrningsläge (Pris/Tid-villkor uppfyllda, Solenergi-villkor uppfyllda inklusive fördröjning, inga smarta lägen aktiva).
    * **Utförande & Förväntat Resultat:** Efter varje scenarioförändring och koordinatoruppdatering kontrolleras att sensorns tillstånd matchar det förväntade aktiva styrningsläget.

### Fil: `tests/test_soc_limit_prevents_charging_start.py`
* **Testfunktion:** `test_charging_is_prevented_by_soc_limit`
    * **Syfte:** Säkerställer att SoC-gränsen har högsta prioritet och kan förhindra att en laddningssession initieras om gränsen redan är nådd.
    * **Scenario/Förutsättningar:** SoC-gränsen är satt (t.ex. 85%). Bilens faktiska SoC rapporteras vara högre (t.ex. 86%). Andra villkor för Pris/Tid-laddning är uppfyllda.
    * **Utförande & Förväntat Resultat:** Koordinatorn uppdateras. Inga tjänsteanrop för att starta laddning eller sätta ström görs. Aktivt styrningsläge förblir `CONTROL_MODE_MANUAL`. Relevant loggmeddelande om att SoC-gränsen nåtts förväntas.

### Fil: `tests/test_huvudstrombrytare_interaktion.py`
* **Testfunktion:** `test_main_switch_off_prevents_charging`
    * **Syfte:** Verifierar att integrationen respekterar huvudströmbrytarens AV-läge och inte försöker starta laddning, även om andra villkor för smart laddning är uppfyllda.
    * **Scenario/Förutsättningar:** Huvudströmbrytaren för laddboxen är satt till `STATE_OFF`. Villkor för Pris/Tid-laddning är uppfyllda.
    * **Utförande & Förväntat Resultat:** Koordinatorn uppdateras. Ingen laddning initieras. Aktivt styrningsläge visar `CONTROL_MODE_MANUAL`. Loggmeddelande indikerar att huvudströmbrytaren är AV.

* **Testfunktion:** `test_manual_turn_off_main_switch_stops_charging`
    * **Syfte:** Verifierar att en pågående smart laddningssession pausas korrekt och styrningsläget återställs om huvudströmbrytaren stängs av manuellt.
    * **Scenario/Förutsättningar:** En Pris/Tid-styrd laddningssession startas. Därefter simuleras att huvudströmbrytaren stängs AV.
    * **Utförande & Förväntat Resultat:** Koordinatorn uppdateras efter att strömbrytaren stängts av. Laddningen pausas (`easee.pause_charging` anropas). Aktivt styrningsläge visar `CONTROL_MODE_MANUAL`. Loggmeddelande indikerar att huvudströmbrytaren är AV.

### Fil: `tests/test_dynamisk_justering_solenergi.py`
* **Testfunktion:** `test_dynamic_current_adjustment_for_solar_charging`
    * **Syfte:** Verifierar den matematiska beräkningen av tillgänglig laddström från solenergi och att koordinatorn korrekt justerar laddarens dynamiska strömgräns när förutsättningarna (husets förbrukning) ändras, med hänsyn till fördröjning.
    * **Scenario/Förutsättningar:**
        * Steg 1: Stor solproduktion (7000 W), låg husförbrukning (500 W), buffert (500 W). Förväntad ström: 8A.
        * Steg 2: Samma solproduktion, men ökad husförbrukning (1500 W). Förväntad ström: 7A.
    * **Utförande & Förväntat Resultat:**
        * Steg 1: Efter initial `async_refresh` och att `SOLAR_SURPLUS_DELAY_SECONDS` har passerat (via `freezer.tick`), ska ytterligare en `async_refresh` leda till att laddning startar (`resume_charging`) och ström sätts till 8A (`set_dynamic_current`). Styrningsläge blir `CONTROL_MODE_SOLAR_SURPLUS`.
        * Steg 2: Husförbrukningen ändras, `async_refresh` körs. Strömmen ska justeras till 7A via `set_dynamic_current`. Styrningsläge förblir `CONTROL_MODE_SOLAR_SURPLUS`.

## Bidra
Se [README.md](README.md) för information om hur du kan bidra till projektet.

## Licens
Detta projekt är licensierat under Apache 2.0-licensen.
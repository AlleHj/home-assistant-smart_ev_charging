# Smart EV Charging – Användarmanual och Testfall

Detta dokument beskriver hur du installerar, konfigurerar och använder den anpassade integrationen "Smart EV Charging" för Home Assistant. Målet med integrationen är att tillhandahålla en flexibel och intelligent styrning av din elbilsladdning, optimerad för både kostnadseffektivitet och hållbarhet.

## Innehållsförteckning
- [1. Introduktion](#1-introduktion)
- [2. Installation och Konfiguration](#2-installation-och-konfiguration)
  - [2.1 Installation](#21-installation)
  - [2.2 Konfigurationsalternativ](#22-konfigurationsalternativ)
    - [2.2.1 Obligatoriska fält](#221-obligatoriska-fält)
    - [2.2.2 Valfria fält (justerbara via alternativflödet)](#222-valfria-fält-justerbara-via-alternativflödet)
- [3. Entiteter som skapas av integrationen](#3-entiteter-som-skapas-av-integrationen)
- [4. Hur styrningslogiken fungerar](#4-hur-styrningslogiken-fungerar)
  - [4.1 Laddningslägen](#41-laddningslägen)
  - [4.2 Kärnfunktioner](#42-kärnfunktioner)
  - [4.3 Prioritering mellan lägen](#43-prioritering-mellan-lägen)
- [5. Testfall](#5-testfall)
  - [5.1 Översikt över Testfiler](#51-översikt-över-testfiler)
  - [5.2 Detaljerade Testfall](#52-detaljerade-testfall)
- [6. Felsökning](#6-felsökning)
- [7. Bidra](#7-bidra)
- [8. Licens](#8-licens)

---

## 1. Introduktion

Smart EV Charging är en Home Assistant Custom Component designad för att optimera laddningen av din elbil genom att ta hänsyn till flera kritiska faktorer: aktuella elpriser, tillgänglig egenproducerad solenergi och bilens State of Charge (SoC). Integrationen syftar till att göra din elbilsladdning smartare, mer kostnadseffektiv och mer miljövänlig genom att automatisera laddningsprocessen baserat på de mest fördelaktiga förhållandena.

Komponenten är byggd för att vara flexibel och integreras sömlöst med befintliga Home Assistant-entiteter som representerar din laddbox, energimätare och bilens status. Den är primärt utvecklad med Easee-laddboxar i åtanke, men dess modulära design kan potentiellt anpassas för andra laddboxar som erbjuder liknande Home Assistant-integrationer.

## 2. Installation och Konfiguration

Följ stegen nedan för att installera och konfigurera Smart EV Charging i din Home Assistant-miljö.

### 2.1 Installation

1.  **Kopiera komponenten**: Ladda ner eller klona innehållet i `custom_components/smart_ev_charging` och placera det i motsvarande `custom_components`-katalog i din Home Assistant-installation. Se till att katalogen är korrekt strukturerad: `path/to/your/homeassistant/config/custom_components/smart_ev_charging/`.
2.  **Starta om Home Assistant**: Efter att filerna är på plats måste du starta om din Home Assistant-instans för att den ska upptäcka den nya komponenten.
3.  **Lägg till Integrationen**:
    * Navigera till **Inställningar** -> **Enheter & tjänster**.
    * Klicka på knappen **+ LÄGG TILL INTEGRATION**.
    * Sök efter **"Smart EV Charging"** i listan.
    * Följ anvisningarna i konfigurationsflödet som visas på skärmen.

### 2.2 Konfigurationsalternativ

All konfiguration sker via Home Assistants användargränssnitt när du lägger till integrationen. De initiala obligatoriska fälten fylls i vid den första installationen, och ytterligare valfria inställningar kan justeras senare via "Alternativ" på integrationskortet.

#### 2.2.1 Obligatoriska fält

Dessa fält är absolut nödvändiga för att integrationen ska kunna fungera korrekt och måste fyllas i under den initiala installationen.

* **Laddbox Entity ID (t.ex. `switch.easee_charger_main_switch`)**: Detta är ID:t för din laddboxens huvudströmbrytare i Home Assistant. Denna `switch`-entitet används för att fjärrstyra start och stopp av laddningen.
* **Laddbox Charger Current Entity ID (t.ex. `number.easee_charger_charging_current_limit`)**: Detta är ID:t för den `number`-entitet som kontrollerar laddboxens strömstyrka i ampere (A). Komponent kommer att justera detta värde för att dynamiskt ändra laddströmmen.
* **SoC Sensor Entity ID (t.ex. `sensor.bilens_soc`)**: ID:t för sensorn som rapporterar bilens aktuella State of Charge (SoC) i procent. Komponent använder detta för att veta när bilen är tillräckligt laddad och bör sluta ladda.
* **Elpris Sensor Entity ID (t.ex. `sensor.nordpool_kwh`)**: ID:t för sensorn som rapporterar det aktuella elpriset i kr/kWh. Komponent använder detta för den prisbaserade laddningslogiken.

#### 2.2.2 Valfria fält (justerbara via alternativflödet)

Dessa fält kan finjusteras efter den initiala installationen genom att gå till **Inställningar** -> **Enheter & tjänster**, hitta Smart EV Charging-integrationen och klicka på "Konfigurera" eller "Alternativ".

* **Car SoC Limit (%)**: Den maximala SoC-procent som bilen ska laddas till. Laddningen avslutas när denna gräns uppnås, oavsett vilket laddningsläge som är aktivt. Standardvärde: `80`.
* **Price Start Charging (kr/kWh)**: Elpris i kr/kWh vid eller under vilket prisbaserad laddning ska starta. Om det aktuella priset är lägre än eller lika med detta värde, och prisbaserad laddning är aktiverad, kommer laddning att initieras.
* **Price Stop Charging (kr/kWh)**: Elpris i kr/kWh vid eller över vilket prisbaserad laddning ska stoppas. Om det aktuella priset är högre än eller lika med detta värde, och prisbaserad laddning är aktiv, kommer laddningen att avbrytas.
* **Minimum Charging Current (A)**: Den lägsta laddströmmen i ampere som laddboxen får dra när smart laddning är aktiv. Laddningen kommer inte att starta eller fortsätta under denna gräns. Standardvärde: `6`.
* **Max Charging Current (A)**: Den maximala laddströmmen i ampere som laddboxen får dra. Denna begränsar den högsta möjliga laddhastigheten. Standardvärde: `16`.
* **Solar Power Entity ID (t.ex. `sensor.solceller_produktion_total`)**: ID:t för din solcellsanläggnings effektsensor (i Watt), som indikerar den totala aktuella solenergiproduktionen. Detta fält är valfritt men nödvändigt för solenergiladdning.
* **House Consumption Entity ID (t.ex. `sensor.hus_förbrukning_total`)**: ID:t för sensorn som indikerar husets totala elförbrukning (i Watt). Detta fält är valfritt men nödvändigt för solenergiladdning, då det används för att beräkna överskott.
* **Solar Charging Stickiness Delay (sekunder)**: Tidsfördröjning i sekunder (t.ex. 300 för 5 minuter). Denna fördröjning säkerställer att solenergiladdningsläget "kvarstår" aktivt även om solenergiöverskottet tillfälligt sjunker under laddningsgränsen. Detta förhindrar onödig och frekvent start/stopp av laddningen vid kortvariga moln eller variationer i produktionen. Standardvärde: `300` (5 minuter).
* **Solar to Price Time Charging Price Limit (kr/kWh)**: Ett specifikt elpris (i kr/kWh). Om det aktuella elpriset är lika med eller lägre än denna gräns, och solenergiladdning är aktiv, kommer laddningsläget automatiskt att byta till prisbaserad laddning. Detta är användbart för att dra nytta av mycket låga elpriser när de inträffar, oavsett tillgänglig solenergi, för att maximera besparingarna.

## 3. Entiteter som skapas av integrationen

Integrationen skapar automatiskt följande 6 entiteter i Home Assistant som du kan interagera med och övervaka för att styra de smarta laddningsfunktionerna. Alla dessa entiteter kommer att ha "Smart EV Charging" som prefix i sitt namn i användargränssnittet, och deras ID:n följer mönstret `[domän].smart_ev_charging_[namn]`.

* **Select (`select.smart_ev_charging_charging_mode`)**: "Smart EV Charging Aktivt Styrningsläge" - En `select`-entitet som låter dig välja det primära laddningsläget: "Pris", "Solenergi" eller "Av".
* **Switch (`switch.smart_ev_charging_charging_switch`)**: "Smart EV Charging Huvudströmbrytare" - En `switch`-entitet för att aktivera/avaktivera all smart laddningslogik som tillhandahålls av integrationen. Om denna är AV, kommer inga automatiska laddningsbeslut att fattas.
* **Switch (`switch.smart_ev_charging_connection_override`)**: "Smart EV Charging Anslutningsåsidosättning" - En `switch`-entitet som kan aktiveras manuellt för att åsidosätta laddboxens rapporterade anslutningsstatus, t.ex. om laddboxen felaktigt säger att den är frånkopplad trots att kabeln är i.
* **Sensor (`sensor.smart_ev_charging_active_control_mode`)**: "Smart EV Charging Aktivt Kontrolläge" - En `sensor`-entitet som dynamiskt visar vilket laddningsläge (`Pris`, `Solenergi` eller `Av`) som för närvarande är aktivt och kontrollerar laddningen.
* **Number (`number.smart_ev_charging_minimum_charging_current`)**: "Smart EV Charging Lägsta laddström (A)" - En `number`-entitet för att ställa in den lägsta tillåtna laddströmmen i Ampere.
* **Number (`number.smart_ev_charging_max_charging_current`)**: "Smart EV Charging Högsta laddström (A)" - En `number`-entitet för att ställa in den högsta tillåtna laddströmmen i Ampere.

## 4. Hur styrningslogiken fungerar

Kärnan i integrationen är `SmartEVChargingCoordinator` som periodiskt utvärderar alla indata från de konfigurerade entiteterna och fattar intelligenta beslut om laddningen ska starta, stoppa eller justeras.

### 4.1 Laddningslägen

Komponenten stöder två huvudlägen för automatisk laddning, vilka väljs via `select.smart_ev_charging_charging_mode`:

* **"Pris" (Price Time)**:
    * Om detta läge är valt och `switch.smart_ev_charging_charging_switch` är PÅ.
    * Laddningen initieras när det aktuella elpriset (`Elpris Sensor Entity ID`) är lika med eller under `Price Start Charging`-gränsen.
    * Laddningen stoppas när elpriset är lika med eller över `Price Stop Charging`-gränsen.
    * Laddströmmen sätts till `Max Charging Current` (t.ex. 16A) när laddning är aktiv i detta läge.

* **"Solenergi" (Solar Charging)**:
    * Om detta läge är valt, `switch.smart_ev_charging_charging_switch` är PÅ, och "Pris"-läge är *inte* aktivt (t.ex. p.g.a. högt pris eller schema).
    * Laddningen försöker använda överskottsenergi från solceller. Överskottet beräknas som (`Solar Power Entity ID` - `House Consumption Entity ID`).
    * Laddning initieras endast om överskottet är tillräckligt för att uppnå `Minimum Charging Current` och detta överskott har varit stabilt över `Solar Charging Stickiness Delay`.
    * Laddströmmen anpassas dynamiskt efter tillgängligt överskott, för att maximera egenkonsumtion av solel.

### 4.2 Kärnfunktioner

Utöver laddningslägen hanteras följande kritiska villkor kontinuerligt:

* **SoC-gräns (State of Charge)**: Har högsta prioritet. Om bilens aktuella SoC (`SoC Sensor Entity ID`) når eller överskrider den konfigurerade `Car SoC Limit (%)`, kommer all smart laddning att förhindras eller pausas omedelbart.
* **Huvudströmbrytare (`switch.smart_ev_charging_charging_switch`)**: Om denna `switch` är AV, kommer ingen smart laddning att ske, oavsett andra inställningar eller förhållanden. Den fungerar som en övergripande "kill-switch" för integrationens automatik.
* **Anslutningsåsidosättning (`switch.smart_ev_charging_connection_override`)**: Om laddboxen rapporterar sig vara frånkopplad (`disconnected`) men laddkabeln är ansluten, kommer denna switch automatiskt att slås PÅ. När den är PÅ åsidosätter den laddboxens `disconnected`-status, vilket kan möjligöra manuell laddning om ett problem med laddboxens egen statusrapportering uppstått. Om kabeln kopplas ur, återställs switchen till AV.

### 4.3 Prioritering mellan lägen

Styrningslogiken följer en tydlig prioriteringsordning för att fatta beslut om laddning:

1.  **SoC-gräns:** Har den absolut högsta prioriteten. Om bilens SoC överstiger den inställda gränsen, kommer all automatisk laddning att stoppas/förhindras omedelbart, oavsett andra förhållanden.
2.  **Huvudströmbrytare (`charging_switch`):** Näst högsta prioritet. Om denna är AV, kommer inga smarta laddningsbeslut att fattas.
3.  **"Pris" (Price Time)-läge:** Om "Pris"-läge är valt via `select`-entiteten, och dess villkor (lågt pris, schema om tillämpligt) är uppfyllda, prioriteras detta läge.
4.  **"Solenergi" (Solar Charging)-läge:** Om "Solenergi"-läge är valt via `select`-entiteten, och "Pris"-läge *inte* är aktivt (t.ex. p.g.a. för högt pris), kan solenergiladdning aktiveras om dess villkor (tillräckligt överskott) är uppfyllda. En särskild gräns (`Solar to Price Time Charging Price Limit`) kan dock göra att "Pris"-läge tar över även från en aktiv solenergiladdning om elpriset blir extremt lågt.

Om inga smarta lägen är aktiva eller deras villkor uppfylls, går laddningen över till att inte styras av integrationen (d.v.s. manuell kontroll eller vad laddarens egna eventuella scheman dikterar).

## 5. Testfall

Nedan beskrivs de automatiska tester som har utvecklats för att säkerställa integrationens funktionalitet, robusthet och korrekta beteende under olika förhållanden. Dessa tester körs med `pytest` och `pytest-homeassistant-custom-component` testramverk. De simulerar Home Assistant-miljön och interagerar med komponentens logik för att verifiera dess svar.

### 5.1 Översikt över Testfiler

* `test_active_control_mode_sensor.py`: Tester för sensorn som visar aktuell kontrolläge (Pris, Solenergi, Av).
* `test_config_flow_and_options_persistence.py`: Tester för konfigurationsflödet och att alternativ sparas korrekt.
* `test_connection_override.py`: Tester för funktionen som åsidosätter laddboxens status.
* `test_coordinator.py`: Tester för datakoordinatorn som hanterar uppdateringar och logik.
* `test_dynamisk_justering_solenergi.py`: Tester för dynamisk justering av laddström baserat på solenergiproduktion.
* `test_huvudstrombrytare_interaktion.py`: Tester för interaktion med huvudströmbrytare (charging switch).
* `test_init.py`: Grundläggande tester för komponentens initiering.
* `test_loggning_vid_frånkoppling.py`: Tester för att verifiera loggning vid frånkoppling av laddboxen.
* `test_soc_limit_prevents_charging_start.py`: Tester för att bekräfta att laddning inte startar om SoC-gränsen uppnåtts.
* `test_solar_charging_stickiness.py`: Tester för att säkerställa att solenergiladdningsläget "kvarstår" även vid kortvariga variationer.
* `test_solar_to_price_time_on_price_drop.py`: Tester för övergång från solenergiladdning till prisbaserad laddning vid prissänkning.
* `test_solar_to_price_time_transition.py`: Tester för övergången mellan solenergiladdning och prisbaserad laddning.
* `test_solenergi_justering.py`: Ytterligare tester för justering av laddström baserat på solenergi.
* `test_solenergiladdning_livscykel.py`: Tester som simulerar en komplett livscykel för solenergiladdning.

### 5.2 Detaljerade Testfall

Här följer en detaljerad genomgång av varje testfall, dess syfte, förväntade beteende och resultat.

#### `test_active_control_mode_sensor.py`

**Testar:** Funktionaliteten hos sensorn `active_control_mode` som indikerar vilket laddningsläge som är aktivt (Pris, Solenergi, Av).

* **`test_active_control_mode_sensor_initial_state`**
    * **Vad testas:** Att sensorn `active_control_mode` initialt sätts till "Av" när komponenten laddas.
    * **Hur det är tänkt att fungera:** Komponentens standardläge är avstängt, och sensorn ska reflektera detta korrekt direkt vid uppstart.
    * **Förväntat resultat:** Sensorns tillstånd är `STATE_OFF` (strängen "Av").

* **`test_active_control_mode_sensor_updates_on_price_time`**
    * **Vad testas:** Att sensorn uppdateras till "Pris" när laddningsläget ändras till prisbaserad laddning.
    * **Hur det är tänkt att fungera:** När `charging_mode` ändras till `CHARGING_MODE_PRICE_TIME` via `select`-entiteten, ska `active_control_mode`-sensorn omedelbart spegla detta nya tillstånd.
    * **Förväntat resultat:** Sensorns tillstånd ändras till `STATE_PRICE_TIME` (strängen "Pris").

* **`test_active_control_mode_sensor_updates_on_solar_charging`**
    * **Vad testas:** Att sensorn uppdateras till "Solenergi" när laddningsläget ändras till solenergiladdning.
    * **Hur det är tänkt att fungera:** När `charging_mode` ändras till `CHARGING_MODE_SOLAR` via `select`-entiteten, ska `active_control_mode`-sensorn omedelbart spegla detta nya tillstånd.
    * **Förväntat resultat:** Sensorns tillstånd ändras till `STATE_SOLAR` (strängen "Solenergi").

* **`test_active_control_mode_sensor_updates_on_off`**
    * **Vad testas:** Att sensorn uppdateras till "Av" när laddningsläget ändras till avstängt.
    * **Hur det är tänkt att fungera:** När `charging_mode` ändras till `STATE_OFF` via `select`-entiteten, ska `active_control_mode`-sensorn omedelbart spegla detta nya tillstånd. Detta testar även återgång till standardläge.
    * **Förväntat resultat:** Sensorns tillstånd ändras till `STATE_OFF` (strängen "Av").

#### `test_config_flow_and_options_persistence.py`

**Testar:** Konfigurationsflödet (UI-baserad installation) och att de inställningar som görs i flödet sparas korrekt och används av integrationen.

* **`test_full_config_flow`**
    * **Vad testas:** En fullständig installation av integrationen via konfigurationsflödet, inklusive att alla nödvändiga steg genomförs och att inställningarna sparas korrekt i en `ConfigEntry`.
    * **Hur det är tänkt att fungera:**
        1.  Initialisering av konfigurationsflödet (`async_step_user`).
        2.  Simulering av att användaren fyller i alla obligatoriska fält (laddbox-ID, SoC-sensor-ID, elpris-sensor-ID, m.fl.).
        3.  Bekräftelse att flödet slutförs framgångsrikt (`FlowResultType.CREATE_ENTRY`).
        4.  Verifiering att en `ConfigEntry` skapas med de angivna uppgifterna.
        5.  Kontroll att integrationen laddas korrekt i Home Assistant med den nya konfigurationen.
    * **Förväntat resultat:** En lyckad installation (`result["type"] == FlowResultType.CREATE_ENTRY`), och att den skapade `config_entry` innehåller de angivna ID:n för laddbox, SoC-sensor och elpris-sensor under `data`.

* **`test_options_flow`**
    * **Vad testas:** Att befintliga konfigurationsinställningar kan ändras via alternativflödet i Home Assistant och att dessa ändringar persisterar och appliceras av integrationen.
    * **Hur det är tänkt att fungera:**
        1.  Initialisering av en befintlig `ConfigEntry` och laddning av integrationen.
        2.  Starta ett alternativflöde (`async_step_init`).
        3.  Simulering av att användaren ändrar en specifik inställning (t.ex. `minimum_charging_current`).
        4.  Bekräftelse att alternativflödet slutförs framgångsrikt (`FlowResultType.ABORT` med `reason="create_entry"`).
        5.  Verifiering att ändringen sparas korrekt i `config_entry.options`.
        6.  Kontroll att integrationen uppdateras och använder den nya inställningen.
    * **Förväntat resultat:** Alternativen uppdateras korrekt, och den ändrade laddningshastigheten (t.ex. `minimum_charging_current`) speglas i `config_entry.options`.

* **`test_reconfigure_flow`**
    * **Vad testas:** Möjligheten att omkonfigurera en befintlig integration, t.ex. om anslutningsdetaljer eller sensor-ID:n behöver ändras. Detta testar flödets robusthet vid ändringar.
    * **Hur det är tänkt att fungera:** Användaren kan initiera en omkonfigurering, ange nya uppgifter, och integrationen ska anpassa sig därefter, potentiellt genom att ladda om sig själv.
    * **Förväntat resultat:** Konfigurationsflödet tillåter omkonfigurering, och de nya värdena sparas och integrationen uppdateras utan fel.

#### `test_connection_override.py`

**Testar:** Funktionerna för att åsidosätta laddboxens anslutningsstatus (`connection_override` switch) och hur det påverkar laddningslogiken, särskilt vid problem med laddboxens rapportering.

* **`test_connection_override_switch`**
    * **Vad testas:** Att `connection_override` switchen skapas korrekt i Home Assistant och kan slås på och av manuellt.
    * **Hur det är tänkt att fungera:** Switchen ska vara avstängd (`STATE_OFF`) initialt. Ett anrop till `turn_on` ska ändra dess tillstånd till `STATE_ON`, och ett anrop till `turn_off` ska återställa det till `STATE_OFF`.
    * **Förväntat resultat:** Switchens tillstånd ändras korrekt från `STATE_OFF` till `STATE_ON` och sedan tillbaka till `STATE_OFF` vid respektive tjänstanrop.

* **`test_connection_override_activates_when_charger_disconnected`**
    * **Vad testas:** Att `connection_override` aktiveras automatiskt när laddboxen rapporterar att den är frånkopplad (`disconnected`), men laddkabeln är ansluten (`is_cable_connected` är `True`). Detta simulerar ett vanligt scenario där laddboxen tappar intern kommunikation med bilen men fysiskt är ansluten.
    * **Hur det är tänkt att fungera:** Om laddboxens anslutningsstatus ändras till `disconnected` samtidigt som `is_cable_connected` förblir `True`, ska `connection_override` automatiskt sättas till `ON`.
    * **Förväntat resultat:** `connection_override` switchens tillstånd ändras till `STATE_ON` efter att laddboxens status uppdaterats.

* **`test_connection_override_deactivates_when_charger_connected`**
    * **Vad testas:** Att `connection_override` deaktiveras automatiskt när laddboxen åter rapporterar att den är ansluten (`connected`), och laddkabeln fortfarande är ansluten. Detta testar att systemet återgår till normalt beteende när problemet är löst.
    * **Hur det är tänkt att fungera:** Om laddboxens anslutningsstatus ändras tillbaka till `connected`, och `is_cable_connected` är `True`, ska `connection_override` sättas till `OFF`.
    * **Förväntat resultat:** `connection_override` switchens tillstånd ändras till `STATE_OFF` efter att laddboxens status återgått till ansluten.

* **`test_connection_override_resets_when_cable_disconnected`**
    * **Vad testas:** Att `connection_override` återställs (stängs av) om laddkabeln kopplas ur, oavsett om `connection_override` var aktiv eller inte. Detta säkerställer att åsidosättningen inte kvarstår i onödan.
    * **Hur det är tänkt att fungera:** Oavsett `connection_override`s nuvarande tillstånd, om laddboxens `is_cable_connected` blir `False`, ska `connection_override` automatiskt stängas av.
    * **Förväntat resultat:** `connection_override` switchens tillstånd ändras till `STATE_OFF`.

* **`test_connection_override_prevents_auto_start_when_active`**
    * **Vad testas:** Att laddning inte startar automatiskt när `connection_override` är aktiv, även om alla andra förhållanden för automatisk laddning är uppfyllda (t.ex. pris/solenergi är optimalt). Detta förhindrar oönskad laddning vid en potentiell laddboxbugg.
    * **Hur det är tänkt att fungera:** Om `connection_override` är `ON`, ska laddboxen inte slås på automatiskt av Smart EV Charging-komponenten, även om `charging_switch` är på och det valda laddningsläget indikerar laddning.
    * **Förväntat resultat:** `mock_ev_charger.turn_on` anropas *inte* under testet, vilket bekräftar att `connection_override` blockerar automatisk start.

#### `test_coordinator.py`

**Testar:** Kärnlogiken i `SmartEVChargingCoordinator`, som ansvarar för att hämta data från olika källor, bearbeta den, och fatta beslut om laddning samt uppdatera Home Assistant-entiteter.

* **`test_coordinator_data_fetch`**
    * **Vad testas:** Att koordinatorn framgångsrikt hämtar den nödvändiga data från de konfigurerade sensorerna (SoC, elpris, solenergi, husförbrukning) och laddboxen.
    * **Hur det är tänkt att fungera:** Vid varje uppdateringscykel ska koordinatorn anropa mockade metoder eller Home Assistant-tjänster för att hämta aktuell status för laddbox, SoC-sensor, elpris-sensor, solenergisensor och husförbrukningssensor.
    * **Förväntat resultat:** `mock_ev_charger.is_connected`, `mock_ev_charger.is_charging`, `mock_ev_charger.is_cable_connected` samt `hass.states.get` (för sensorvärden) anropas med de förväntade entitets-ID:na.

* **`test_coordinator_updates_all_data`**
    * **Vad testas:** Att koordinatorn uppdaterar all sin interna, bearbetade data vid varje framgångsrik uppdateringscykel.
    * **Hur det är tänkt att fungera:** När `async_update_data` anropas och lyckas hämta alla källvärden, ska koordinatorns interna `data`-dictionary eller motsvarande attribut innehålla de senast hämtade och bearbetade värdena för laddboxens anslutningsstatus, laddstatus, SoC, aktuellt elpris, solenergiproduktion och hushållsförbrukning.
    * **Förväntat resultat:** `coordinator.data` innehåller uppdaterade och korrekta värden för alla relevanta mätpunkter efter en uppdatering.

* **`test_coordinator_handles_missing_sensor_data`**
    * **Vad testas:** Att koordinatorn graciöst hanterar fall där sensordata (t.ex. SoC eller elpris) saknas, är ogiltig (`None`), eller har ett tillstånd som inte kan parsas till ett numeriskt värde.
    * **Hur det är tänkt att fungera:** Om en sensor inte returnerar ett giltigt tillstånd, ska koordinatorn inte krascha. Istället ska den antingen tilldela ett standardvärde (t.ex. `0` eller `None`) till den interna variabeln för den sensorn, eller på annat sätt undvika fel, och fortsätta fungera med de tillgängliga uppgifterna.
    * **Förväntat resultat:** Inga ohanterade undantag uppstår under testet. Relaterade variabler i koordinatorn som beror på den saknade/ogiltiga sensordatan får ett `None` eller standardvärde, och loggning sker vid behov.

* **`test_coordinator_charging_thresholds`**
    * **Vad testas:** Att laddningsbeslut (starta/stoppa) baseras korrekt på de definierade tröskelvärdena för prisbaserad laddning (`price_start_charging` och `price_stop_charging`).
    * **Hur det är tänkt att fungera:** Om laddningsläget är "Pris":
        * När elpriset är lägre än eller lika med `price_start_charging` ska laddning triggas (om inte andra villkor hindrar).
        * När elpriset är högre än eller lika med `price_stop_charging` ska laddning stoppas.
    * **Förväntat resultat:** `mock_ev_charger.turn_on` eller `mock_ev_charger.turn_off` anropas korrekt baserat på simulerade elpriser och tröskelvärden.

* **`test_coordinator_car_soc_limit`**
    * **Vad testas:** Att koordinatorn strikt respekterar den konfigurerade SoC-gränsen (`car_soc_limit`) för laddning.
    * **Hur det är tänkt att fungera:** Om bilens SoC överstiger `car_soc_limit`, ska koordinatorn förhindra att laddning startar. Om laddning pågår och SoC-gränsen nås, ska koordinatorn initiera ett stopp av laddningen.
    * **Förväntat resultat:** `mock_ev_charger.turn_off` anropas om SoC är för högt (och laddning pågår). `mock_ev_charger.turn_on` anropas *inte* om SoC redan är över gränsen.

* **`test_coordinator_charger_power_limit`**
    * **Vad testas:** Att koordinatorn korrekt beräknar och justerar laddningsströmmen baserat på den tillgängliga effekten, oavsett om det är från solenergiöverskott eller andra förhållanden.
    * **Hur det är tänkt att fungera:** Koordinatorn ska kalla `mock_ev_charger.set_charging_current` med det beräknade optimala ampere-värdet, med hänsyn till `minimum_charging_current` och `max_charging_current`.
    * **Förväntat resultat:** `mock_ev_charger.set_charging_current` anropas med korrekta, beräknade värden som ligger inom de definierade gränserna.

* **`test_coordinator_solarenergy_modes`**
    * **Vad testas:** Att koordinatorn korrekt hanterar och prioriterar solenergiladdningslägena, inklusive beräkning av överskottseffekt.
    * **Hur det är tänkt att fungera:** Om solenergiladdning är aktiverad, ska koordinatorn beräkna nettoeffekten (solenergiproduktion minus hushållsförbrukning) och därefter besluta om laddning ska ske och med vilken ström, med hänsyn till `solar_charging_stickiness_delay`.
    * **Förväntat resultat:** Koordinatorn beräknar laddström baserat på solenergiöverskott och fattar laddningsbeslut (starta/stoppa/justera ström) som optimerar användningen av solel.

#### `test_dynamisk_justering_solenergi.py`

**Testar:** Den dynamiska justeringen av laddström baserat på solenergiöverskott, inklusive olika scenarier för produktion och förbrukning och hur komponenten svarar på dessa ändringar.

* **`test_dynamisk_justering_solenergi_full_laddning`**
    * **Vad testas:** Att laddningsströmmen justeras till maximalt när solenergiöverskottet är tillräckligt högt för att hantera den maximala laddströmmen (t.ex. 16A).
    * **Hur det är tänkt att fungera:** Med ett stort positivt solenergiöverskott (produktion långt över förbrukning plus laddningsbehov) ska laddströmmen sättas till det konfigurerade maxvärdet (`max_charging_current`).
    * **Förväntat resultat:** `mock_ev_charger.set_charging_current` anropas med `16` ampere, vilket indikerar full laddning.

* **`test_dynamisk_justering_solenergi_halv_laddning`**
    * **Vad testas:** Att laddningsströmmen justeras proportionerligt när solenergiöverskottet är måttligt och räcker för att ladda, men inte nödvändigtvis vid maximal hastighet.
    * **Hur det är tänkt att fungera:** Med ett måttligt positivt solenergiöverskott (tillräckligt för laddning men inte för maxström) ska laddströmmen justeras till ett värde mellan `minimum_charging_current` och `max_charging_current` baserat på överskottet.
    * **Förväntat resultat:** `mock_ev_charger.set_charging_current` anropas med ett beräknat ampere-värde (t.ex. 10) som är proportionerligt mot solenergiöverskottet.

* **`test_dynamisk_justering_solenergi_ingen_laddning`**
    * **Vad testas:** Att laddningen stoppas eller förhindras från att starta när solenergiöverskottet är otillräckligt, noll eller negativt (d.v.s. hushållet förbrukar mer än solcellerna producerar).
    * **Hur det är tänkt att fungera:** Om solenergiöverskottet är under den tröskel som krävs för `minimum_charging_current` (eller negativt), ska laddningen stängas av eller inte starta alls.
    * **Förväntat resultat:** `mock_ev_charger.turn_off` anropas.

* **`test_dynamisk_justering_solenergi_med_min_laddstrom`**
    * **Vad testas:** Att systemet korrekt respekterar den konfigurerade `minimum_charging_current` när solenergiladdning är aktiv. Laddning ska antingen ske vid minst denna ström, eller inte alls.
    * **Hur det är tänkt att fungera:** Om den beräknade laddströmmen baserad på solenergiöverskott är lägre än `minimum_charging_current` men fortfarande positiv, ska laddningen antingen stängas av (om ingen marginal tillåts) eller sättas till `minimum_charging_current`.
    * **Förväntat resultat:** Antingen `mock_ev_charger.turn_off` eller `mock_ev_charger.set_charging_current(6)` anropas, beroende på de exakta tröskelvärdena och implementeringslogiken för minimiström.

* **`test_dynamisk_justering_solenergi_avstangd_solenergi`**
    * **Vad testas:** Att dynamisk justering av laddström baserad på solenergi *inte* sker när solenergiladdningsläget är avstängt (t.ex. "Pris" eller "Av" är valt).
    * **Hur det är tänkt att fungera:** Om `charging_mode` är inställt på något annat än `CHARGING_MODE_SOLAR`, ska solenergiöverskottet inte påverka laddningsströmmen dynamiskt via den solbaserade logiken. Laddningsbeslut ska istället fattas baserat på det valda läget (t.ex. pris).
    * **Förväntat resultat:** `mock_ev_charger.set_charging_current` anropas *inte* för justering baserad på solenergi när solenergiläget är inaktivt.

#### `test_huvudstrombrytare_interaktion.py`

**Testar:** Interaktionen mellan komponentens huvudströmbrytare (`charging_switch`) och laddboxen, inklusive både manuell styrning via Home Assistant-tjänster och automatisk avstängning under specifika förhållanden.

* **`test_charging_switch_on_off`**
    * **Vad testas:** Att huvudströmbrytaren (`charging_switch`) korrekt kan slås på och av via Home Assistant-tjänster (`homeassistant.turn_on`, `homeassistant.turn_off`), och att laddboxen (`mock_ev_charger`) reagerar därefter.
    * **Hur det är tänkt att fungera:** När `charging_switch` slås på, ska `mock_ev_charger.turn_on` anropas. När `charging_switch` slås av, ska `mock_ev_charger.turn_off` anropas.
    * **Förväntat resultat:** Switchens tillstånd ändras till `STATE_ON` vid `turn_on` och till `STATE_OFF` vid `turn_off`, och de motsvarande metoderna på `mock_ev_charger` kallas exakt en gång per ändring.

* **`test_charging_switch_auto_off_when_cable_disconnected`**
    * **Vad testas:** Att huvudströmbrytaren automatiskt stängs av om laddkabeln kopplas bort från bilen eller laddboxen.
    * **Hur det är tänkt att fungera:** Om laddboxens status för `is_cable_connected` ändras till `False` (kabel borttagen), ska `charging_switch` automatiskt ändra sitt tillstånd till `STATE_OFF`.
    * **Förväntat resultat:** `charging_switch` tillstånd ändras till `STATE_OFF` efter att `is_cable_connected` blir `False`.

* **`test_charging_switch_auto_off_when_soc_limit_reached`**
    * **Vad testas:** Att huvudströmbrytaren automatiskt stängs av om bilens SoC (State of Charge) når eller överskrider den konfigurerade `car_soc_limit` under pågående laddning.
    * **Hur det är tänkt att fungera:** Om bilens SoC rapporteras som lika med eller högre än `car_soc_limit` medan `charging_switch` är `ON`, ska `charging_switch` automatiskt slås av.
    * **Förväntat resultat:** `charging_switch` tillstånd ändras till `STATE_OFF` när SoC-gränsen uppnås.

* **`test_charging_switch_auto_off_when_charger_disconnected`**
    * **Vad testas:** Att huvudströmbrytaren automatiskt stängs av om laddboxen blir frånkopplad (t.ex. tappar ström eller nätverksanslutning), förutsatt att `connection_override` inte är aktiv.
    * **Hur det är tänkt att fungera:** Om laddboxens `is_connected` status ändras till `False`, och `connection_override` är `OFF`, ska `charging_switch` automatiskt slås av.
    * **Förväntat resultat:** `charging_switch` tillstånd ändras till `STATE_OFF` när laddboxen rapporterar `disconnected`.

#### `test_init.py`

**Testar:** Komponentens initieringsprocess och hur den hanterar olika scenarier vid uppstart och avlastning i Home Assistant.

* **`test_setup_entry_success`**
    * **Vad testas:** Att integrationen laddas korrekt under Home Assistant-uppstart baserat på en `ConfigEntry`, och att alla associerade entiteter (sensorer, nummer, switchar) läggs till i Home Assistant.
    * **Hur det är tänkt att fungera:** `async_setup_entry` ska returnera `True`, vilket indikerar en framgångsrik laddning. Detta innebär att koordinatorn initieras, och de förväntade Home Assistant-plattformarna (`sensor`, `number`, `switch`) ska laddas och lägga till sina respektive entiteter.
    * **Förväntat resultat:** `async_setup_entry` returnerar `True`, och de mockade plattformarna (representerade av `mock_setup_platform`) anropas med rätt domäner och entitetsdata, vilket bekräftar att entiteterna registrerats.

* **`test_unload_entry_success`**
    * **Vad testas:** Att integrationen kan laddas ur korrekt från Home Assistant, och att alla dess skapade entiteter och lyssnare tas bort rent.
    * **Hur det är tänkt att fungera:** `async_unload_entry` ska returnera `True`, vilket indikerar en framgångsrik avlastning. Detta inkluderar att alla plattformar och deras entiteter avregistreras, samt att koordinatorn stängs ner på ett säkert sätt.
    * **Förväntat resultat:** `async_unload_entry` returnerar `True`, och `mock_unload_platform` anropas för alla relevanta plattformar, vilket bekräftar att entiteterna avregistreras.

* **`test_reload_entry_success`**
    * **Vad testas:** Att integrationen kan laddas om utan problem via Home Assistants omladdningsfunktion. Detta är viktigt för utveckling och felsökning utan att behöva starta om hela Home Assistant.
    * **Hur det är tänkt att fungera:** En lyckad `unload` följt av en lyckad `setup` bör emulera en korrekt omladdning. Systemet ska inte hamna i ett korrupt tillstånd.
    * **Förväntat resultat:** Både `async_unload_entry` och `async_setup_entry` returnerar `True` i följd, vilket bekräftar att integrationen kan laddas om framgångsrikt.

#### `test_loggning_vid_frånkoppling.py`

**Testar:** Att korrekta loggmeddelanden genereras när laddboxen kopplas bort från bilen eller nätverket, med särskild hänsyn till om `connection_override` switchen är aktiv eller inte. Detta är viktigt för felsökning och för att förstå systemets status.

* **`test_logging_on_disconnect_without_override`**
    * **Vad testas:** Att ett specifikt varningsloggmeddelande genereras när laddboxen kopplas bort (`is_connected` blir `False`), och `connection_override` *inte* är aktiv (`OFF`). Detta indikerar ett oväntat bortfall av laddboxen.
    * **Hur det är tänkt att fungera:** När laddboxens anslutningsstatus ändras till `disconnected`, och `connection_override` är `OFF`, ska ett loggmeddelande på `WARNING` nivå genereras som informerar om att laddboxen är frånkopplad och att åsidosättning inte är aktiv.
    * **Förväntat resultat:** Ett varningsmeddelande om frånkopplad laddbox loggas en gång via `caplog`.

* **`test_logging_on_disconnect_with_override`**
    * **Vad testas:** Att ett annat, mindre allvarligt (eller inget varningsmeddelande) loggmeddelande genereras när laddboxen kopplas bort, men `connection_override` är aktiv (`ON`). Detta indikerar att systemet är medvetet om problemet och åsidosätter det.
    * **Hur det är tänkt att fungera:** När laddboxens anslutningsstatus ändras till `disconnected`, men `connection_override` är `ON`, ska ett loggmeddelande som indikerar att åsidosättningen är aktiv loggas istället för den vanliga varningsmeddelandet. Detta förhindrar att loggen fylls med varningar när en åsidosättning avsiktligt används.
    * **Förväntat resultat:** Ett informationsmeddelande om att `connection_override` är aktiv loggas, eller att varningsmeddelandet från föregående test *inte* loggas, vilket indikerar korrekt hantering av loggningsprioritet.

#### `test_soc_limit_prevents_charging_start.py`

**Testar:** Att laddning inte initieras eller tillåts fortsätta när bilens State of Charge (SoC) redan har uppnått eller överskridit den konfigurerade `car_soc_limit`. Detta är en kritisk säkerhets- och optimeringsfunktion för att förhindra överladdning och onödig strömförbrukning.

* **`test_soc_limit_prevents_charging_start`**
    * **Vad testas:** Att automatisk laddning inte startar om bilens SoC är lika med eller över den inställda `car_soc_limit` vid tidpunkten för ett laddningsbeslut.
    * **Hur det är tänkt att fungera:**
        1.  Konfigurera en `car_soc_limit` (t.ex. 80%).
        2.  Simulera att bilens SoC-sensor rapporterar ett värde som är lika med eller över denna gräns (t.ex. 85%).
        3.  Simulera att andra förhållanden (pris eller solenergi) skulle trigga laddning.
        4.  Systemet ska identifiera att SoC-gränsen är nådd och förhindra att `charging_switch` slås på.
    * **Förväntat resultat:** `charging_switch` tillstånd förblir `STATE_OFF`, och `mock_ev_charger.turn_on` anropas *aldrig* under testet, vilket bekräftar att SoC-gränsen korrekt förhindrar start av laddning.

#### `test_solar_charging_stickiness.py`

**Testar:** Att solenergiladdningsläget "kvarstår" (inte stängs av omedelbart) även vid kortvariga dippar i solenergiladdningen. Detta förhindrar att laddningen startar och stoppar frekvent vid tillfälliga moln eller snabba variationer i solelproduktionen, vilket kan vara skadligt för både laddbox och bil.

* **`test_solar_charging_stickiness_during_short_dip`**
    * **Vad testas:** Att laddning i solenergiläge fortsätter trots en tillfällig minskning av solenergiöverskottet under den konfigurerade `solar_charging_stickiness_delay`.
    * **Hur det är tänkt att fungera:**
        1.  Initialt finns tillräckligt solenergiöverskott för att starta laddning.
        2.  Simulera en snabb, kortvarig minskning av solenergiöverskottet (t.ex. ett moln) till under den nivå som normalt skulle stoppa laddningen.
        3.  Bekräfta att laddningen fortsätter under den specificerade `solar_charging_stickiness_delay` utan att stängas av.
    * **Förväntat resultat:** `mock_ev_charger.turn_off` anropas *inte* under den definierade fördröjningen, vilket bekräftar att "stickiness"-mekanismen håller laddningen aktiv trots den tillfälliga dippen.

* **`test_solar_charging_turns_off_after_stickiness_delay`**
    * **Vad testas:** Att laddning i solenergiläge stängs av om det låga solenergiöverskottet kvarstår längre än den konfigurerade `solar_charging_stickiness_delay`.
    * **Hur det är tänkt att fungera:**
        1.  Laddning pågår i solenergiläge.
        2.  Simulera att solenergiöverskottet sjunker under den laddningsaktiverande tröskeln och förblir där.
        3.  Efter att tiden som definieras av `solar_charging_stickiness_delay` har passerat, ska laddningen avbrytas.
    * **Förväntat resultat:** `mock_ev_charger.turn_off` anropas precis efter att `solar_charging_stickiness_delay` har förflutit, vilket validerar att fördröjningen fungerar som en buffert men att laddningen avslutas när överskottet är otillräckligt under längre tid.

#### `test_solar_to_price_time_on_price_drop.py`

**Testar:** Den automatiska övergången från solenergiladdningsläget till det prisbaserade laddningsläget när elpriset sjunker under en fördefinierad tröskel (`solar_to_price_time_charging_price_limit`), även om det fortfarande finns tillräckligt med solenergi för att ladda. Detta testar förmågan att prioritera maximal besparing vid mycket låga elpriser.

* **`test_solar_to_price_time_on_price_drop`**
    * **Vad testas:** Att laddningsläget (`charging_mode`) automatiskt byter från `CHARGING_MODE_SOLAR` till `CHARGING_MODE_PRICE_TIME` när elpriset faller under den konfigurerade tröskeln (`solar_to_price_time_charging_price_limit`), oavsett om solenergi finns tillgänglig eller inte.
    * **Hur det är tänkt att fungera:**
        1.  Initialt är systemet i `CHARGING_MODE_SOLAR` och laddar (eller skulle ladda) med solenergiöverskott.
        2.  Simulera en ändring av elpriset så att det sjunker under `solar_to_price_time_charging_price_limit`.
        3.  Komponenten ska upptäcka detta och automatiskt ändra `charging_mode` till `CHARGING_MODE_PRICE_TIME`.
    * **Förväntat resultat:** `charging_mode` switchen ändras korrekt till `STATE_PRICE_TIME` (strängen "Pris") när elpriset passerar den definierade gränsen.

#### `test_solar_to_price_time_transition.py`

**Testar:** En mer komplex och dynamisk övergång mellan solenergiladdning och prisbaserad laddning baserat på en kombination av pris och solenergi, vilket simulerar realistiska variationer under en dag.

* **`test_solar_to_price_time_transition`**
    * **Vad testas:** Att systemet korrekt kan växla mellan solenergiladdning och prisbaserad laddning under varierande förhållanden, och att det väljer det mest fördelaktiga läget dynamiskt.
    * **Hur det är tänkt att fungera:**
        1.  Starta testet i solenergiladdningsläge med tillräckligt solenergiöverskott för laddning.
        2.  Simulera att elpriset sjunker tillräckligt lågt för att trigga en övergång till prisbaserad laddning (via `solar_to_price_time_charging_price_limit`). Systemet ska byta läge.
        3.  Simulera att elpriset sedan stiger igen till en nivå där prisbaserad laddning inte längre är fördelaktig. Systemet ska då återgå till solenergiladdning (om solenergiöverskott fortfarande finns).
        4.  Slutligen simulera en situation där varken solenergi eller pris är gynnsamt, och laddningen stängs av.
    * **Förväntat resultat:** `charging_mode` switchen växlar korrekt mellan `STATE_SOLAR` och `STATE_PRICE_TIME` baserat på prisändringar och tillgång till solenergi, och stängs sedan av vid ogynnsamma förhållanden.

#### `test_solenergi_justering.py`

**Testar:** Ytterligare detaljerade scenarier för hur laddströmmen justeras baserat på solenergiöverskott och hushållsförbrukning, med fokus på marginaler, effekttak och gränsfall för att säkerställa precision.

* **`test_charging_current_adjustments_with_solar_power`**
    * **Vad testas:** Att laddströmmen (i ampere) justeras exakt och korrekt baserat på det tillgängliga solenergiöverskottet (solproduktion minus husförbrukning) och konvertering till ampere, samt med hänsyn till `minimum_charging_current` och `max_charging_current`.
    * **Hur det är tänkt att fungera:**
        1.  Simulera olika nivåer av solenergiproduktion och hushållsförbrukning.
        2.  Komponenten ska beräkna nettoöverskottet (Watt) och konvertera detta till en rekommenderad laddström i Ampere.
        3.  `mock_ev_charger.set_charging_current` ska anropas med det beräknade värdet, avrundat till närmaste heltal (eller enligt specificerad logik för avrundning av laddström).
    * **Förväntat resultat:** `mock_ev_charger.set_charging_current` anropas med de beräknade optimala ampere-värdena (t.ex. 6A, 10A, 16A) som korrekt reflekterar solenergiöverskottet.

* **`test_charging_current_lower_than_min_amperes`**
    * **Vad testas:** Att laddningen stängs av om den beräknade strömmen, baserad på solenergiöverskott, faller under den konfigurerade `minimum_charging_current`.
    * **Hur det är tänkt att fungera:** Om den beräknade överskottseffekten är så låg att den motsvarar en laddström som är lägre än `minimum_charging_current` (t.ex. under 6A), ska komponenten besluta att stoppa laddningen helt snarare än att ladda ineffektivt.
    * **Förväntat resultat:** `mock_ev_charger.turn_off` anropas, vilket bekräftar att laddningen avbryts när den inte kan upprätthålla minimiströmmen.

* **`test_charging_current_below_target_but_above_min_amperes`**
    * **Vad testas:** Att laddströmmen justeras till `minimum_charging_current` om det tillgängliga solenergiöverskottet inte räcker för en högre ström, men är tillräckligt för att åtminstone uppfylla minimikravet för laddning.
    * **Hur det är tänkt att fungera:** Om den beräknade överskottseffekten tillåter en laddström mellan `minimum_charging_current` och nästa högre steg (t.ex. mellan 6A och 10A), ska laddningen ske vid `minimum_charging_current`.
    * **Förväntat resultat:** `mock_ev_charger.set_charging_current(6)` anropas, vilket visar att systemet väljer den lägsta tillåtna laddströmmen när överskottet är knappt.

* **`test_charging_current_negative_net_power`**
    * **Vad testas:** Att laddningen stängs av omedelbart om det finns ett nettoupptag från elnätet (d.v.s. hushållet förbrukar mer el än solcellerna producerar), även om en mindre solenergiöverskott tidigare fanns.
    * **Hur det är tänkt att fungera:** Om den totala hushållsförbrukningen överstiger solenergiproduktionen, vilket resulterar i en negativ nettoeffekt ("överskott"), ska laddningen stoppas för att undvika att dra dyr nätel.
    * **Förväntat resultat:** `mock_ev_charger.turn_off` anropas, vilket bekräftar att laddningen avslutas vid negativt nettoöverskott.

#### `test_solenergiladdning_livscykel.py`

**Testar:** En fullständig, end-to-end simulering av solenergiladdningens livscykel, från start till stopp, inklusive att simulera variationer i solenergiladdningen. Detta test är avgörande för att verifiera att alla delar av solenergiladdningslogiken samverkar korrekt.

* **`test_solenergiladdning_livscykel_success`**
    * **Vad testas:** En komplett livscykel för solenergiladdning, inklusive anslutning av kabel, start av laddning, dynamisk justering av strömmen baserat på varierande solenergiöverskott, och slutligen stopp av laddning när förhållandena inte längre är gynnsamma.
    * **Hur det är tänkt att fungera:**
        1.  Initialt: Ingen kabel ansluten, laddning avstängd.
        2.  Simulera: Laddkabeln ansluts, det finns ett visst solenergiöverskott. Förvänta att laddningen startar med en grundström.
        3.  Simulera: Solenergiöverskottet ökar. Förvänta att laddströmmen justeras uppåt dynamiskt.
        4.  Simulera: Solenergiöverskottet minskar till en punkt där laddning med minimiström inte längre är möjlig, eller där det är mer lönsamt att sluta ladda.
        5.  Förvänta: Laddningen stängs av.
    * **Förväntat resultat:**
        * `mock_ev_charger.turn_on` kallas när laddning bör starta.
        * `mock_ev_charger.set_charging_current` kallas flera gånger med varierande ampere-värden som dynamiskt anpassas till det simulerade solenergiöverskottet.
        * `mock_ev_charger.turn_off` kallas när solenergiöverskottet inte längre är tillräckligt för att upprätthålla laddning.
        * Systemet ska hantera övergångarna smidigt och fatta korrekta beslut vid varje steg av livscykeln.

## 6. Felsökning

Om du stöter på problem med integrationen, följ dessa steg för felsökning:

* **Aktivera Debug-loggning:** Du kan aktivera mer detaljerad loggning för integrationen via Home Assistants logginställningar eller via integrationens alternativ. Detta ger dig mer information i Home Assistant-loggarna (sök efter `custom_components.smart_ev_charging`).
* **Kontrollera externa sensorer:** Säkerställ att alla sensorer och entiteter du har konfigurerat (elpris, SoC, solenergi, husförbrukning, laddboxens strömbrytare och strömgränser) rapporterar korrekta och tillgängliga värden i Home Assistant. Felsök först de underliggande sensorerna om de inte fungerar som förväntat.
* **Enhets-ID:n för interna entiteter:** De av integrationen skapade entiteterna (switchar, nummer, sensor) får ID:n baserade på det interna `DEFAULT_NAME` ("Smart EV Charging") och deras specifika funktion, t.ex. `switch.smart_ev_charging_charging_switch`. Kontrollera att dessa entiteter finns och har förväntade tillstånd.
* **Kabelanslutning och laddboxstatus:** Verifiera att din laddbox korrekt rapporterar om kabeln är ansluten och om den är i laddningsläge. Om laddboxen rapporterar `disconnected` trots att kabeln är i, kan du prova att använda `connection_override`-switchen för att åsidosätta detta.

## 7. Licens

Detta projekt är licensierat under Apache 2.0-licensen. Se filen `LICENSE` i projektets rotkatalog för fullständig information.
# Hjälp för Avancerad Elbilsladdning Integration

Välkommen till hjälpsektionen för custom component "Avancerad Elbilsladdning" för Home Assistant!
Denna integration syftar till att ge dig en flexibel och intelligent styrning av din elbilsladdning.

## Innehållsförteckning
1.  [Syfte med Integrationen](#1-syfte-med-integrationen)
2.  [Övergripande Funktionalitet](#2-övergripande-funktionalitet)
    * [Prioritetsordning](#prioritetsordning)
3.  [Systemkrav och Externa Beroenden](#3-systemkrav-och-externa-beroenden)
4.  [Konfiguration av Integrationen](#4-konfiguration-av-integrationen)
    * [Initial Konfiguration](#initial-konfiguration)
    * [Ändra Alternativ](#ändra-alternativ)
    * [Förklaring av Konfigurationsparametrar](#förklaring-av-konfigurationsparametrar)
5.  [Entiteter Skapade av Integrationen](#5-entiteter-skapade-av-integrationen)
6.  [Kärnlogik och Styrningsstrategier](#6-kärnlogik-och-styrningsstrategier)
7.  [Felsökning](#7-felsökning)

## 1. Syfte med Integrationen
Målet är att automatiskt styra laddningen av din elbil via en Easee-laddbox (eller potentiellt andra kompatibla laddboxar) baserat på dynamiska kriterier som elpris, tidsscheman, solenergiöverskott och bilens laddningsnivå (SoC). Detta för att optimera laddningskostnader och maximera användningen av egenproducerad solenergi.

## 2. Övergripande Funktionalitet
Integrationen erbjuder flera smarta laddningslägen och en övergripande laddningsgräns (SoC).

### Prioritetsordning
Styrningen sker enligt följande prioritet:
1.  **Laddningsgräns (SoC - State of Charge)**: (Högst Prioritet) Om bilens SoC når den inställda gränsen, pausas all smart laddning.
2.  **Pris/Tid-styrd Smartladdning**: (Andra Prioritet, om SoC tillåter) Laddar när definierade tidsscheman är aktiva och aktuellt spotpris är under inställt maxvärde.
3.  **Solenergiladdning**: (Tredje Prioritet, om SoC och Pris/Tid tillåter) Använder solenergiöverskott för laddning när dess schema är aktivt och tillräckligt överskott finns.

Integrationen skapar egna entiteter (switchar, nummerinmatningar, sensorer) för att hantera dessa funktioner och ge översikt.

## 3. Systemkrav och Externa Beroenden
* En fungerande Home Assistant-installation.
* **Easee EV Charger-integrationen**: Korrekt installerad och konfigurerad för din Easee-laddbox.
* Diverse sensorer och hjälpare som du behöver skapa i Home Assistant och sedan länka till under konfigurationen av denna integration.

## 4. Konfiguration av Integrationen

### Initial Konfiguration
När du lägger till "Avancerad Elbilsladdning" från integrationssidan i Home Assistant, kommer du att guidas genom en konfigurationsdialog.

### Ändra Alternativ
Efter installationen kan du ändra inställningarna genom att gå till integrationens sida och klicka på "Alternativ".

### Förklaring av Konfigurationsparametrar

Alla entiteter du väljer här måste redan existera i din Home Assistant-miljö. Du kan skapa dem med t.ex. "Hjälpare" (för scheman, input_number) eller via `template:`-sensorer i din `configuration.yaml`.

#### Obligatoriska Fält:
* **Easee Laddarenhet (`charger_device_id`)**:
    * **Beskrivning**: Välj din Easee-laddboxenhet från listan. Detta är den primära enheten som integrationen kommer att styra.
    * **Krav**: Enhet skapad av Easee-integrationen.
* **Statussensor för Laddaren (`status_sensor_id`)**:
    * **Beskrivning**: Välj den sensor som visar aktuell status för din Easee-laddare (t.ex. `sensor.min_laddbox_status`). Integrationen använder denna för att veta om bilen är ansluten, laddar, pausad etc.
    * **Krav**: En `sensor`-entitet. Exempel: `sensor.easee_uppfart_status`.
* **Huvudströmbrytare för Laddboxen (`charger_enabled_switch_id`)**:
    * **Beskrivning**: Välj den `switch`-entitet som styr huvudströmbrytaren för din Easee-laddbox (t.ex. `switch.min_laddbox_aktiverad`). Integrationen kan automatiskt slå på denna om ett smart laddningsläge är aktivt men brytaren är av.
    * **Krav**: En `switch`-entitet. Exempel: `switch.easee_uppfart_power`.
* **Elprissensor (Spotpris) (`price_sensor_id`)**:
    * **Beskrivning**: Välj den sensor som visar aktuellt el-spotpris. Integrationen försöker tolka enheter som öre/kWh, SEK/kWh, EUR/kWh eller MWh-varianter. Priset används för Pris/Tid-styrd laddning.
    * **Krav**: En `sensor`-entitet. Exempel: `sensor.nordpool_kwh_se3_sek_3_10_025`.

#### Valfria Fält (men rekommenderade för full funktionalitet):
* **Påslagshjälpare (Avgifter/Moms) (`surcharge_helper_id`)**:
    * **Beskrivning**: Valfri. Välj en `sensor` eller `input_number` som representerar totala påslag utöver spotpriset (t.ex. nätavgift, moms, elcertifikat) i kr/kWh eller öre/kWh. Används *endast* för att beräkna den totala kostnaden för en laddningssession (visas i `sensor.avancerad_elbilsladdning_session_kostnad`). Påverkar inte själva laddningsbesluten.
    * **Krav**: En `sensor` eller `input_number`. Om utelämnad, antas påslaget vara 0.
* **Tidsschema för Pris/Tid-laddning (`time_schedule_entity_id`)**:
    * **Beskrivning**: Valfri. Välj en `schedule`-hjälpare. När detta schema är aktivt (PÅ), är Pris/Tid-styrd laddning tillåten (förutsatt att prisvillkoret också är uppfyllt). Om inget schema anges här, anses Pris/Tid-laddning alltid vara tidstillåten (styrs då enbart av pris och huvudswitchen för Pris/Tid).
    * **Krav**: En `schedule`-entitet.
* **Effektsensor för Huset (`house_power_sensor_id`)**:
    * **Beskrivning**: Valfri, men **nödvändig för solenergiladdning**. Välj en sensor som mäter husets totala momentana effektförbrukning i Watt (W) eller kilowatt (kW). Används för att beräkna solenergiöverskott.
    * **Krav**: En `sensor`-entitet med `device_class: power`.
* **Effektsensor för Solproduktion (`solar_production_sensor_id`)**:
    * **Beskrivning**: Valfri, men **nödvändig för solenergiladdning**. Välj en sensor som mäter din solcellsanläggnings totala momentana effektproduktion i Watt (W) eller kilowatt (kW).
    * **Krav**: En `sensor`-entitet med `device_class: power`.
* **Tidsschema för Solenergiladdning (`solar_schedule_entity_id`)**:
    * **Beskrivning**: Valfri. Välj en `schedule`-hjälpare. När detta schema är aktivt (PÅ), är solenergiladdning tillåten (förutsatt att det finns tillräckligt med solöverskott). Om inget schema anges, anses solenergiladdning alltid vara tidstillåten (styrs då enbart av överskott och huvudswitchen för solenergiladdning).
    * **Krav**: En `schedule`-entitet.
* **Sensor för Laddboxens Max Strömgräns (`charger_max_current_limit_sensor_id`)**:
    * **Beskrivning**: Valfri. Välj en sensor som visar den faktiska dynamiska eller statiska strömbegränsningen (i Ampere) som är satt på laddboxen (t.ex. via Easee-appen eller annan automation). Används för att veta den faktiska maximala strömmen som kan användas, speciellt för Pris/Tid-laddning. Om utelämnad, antar integrationen en standardgräns (f.n. 16A).
    * **Krav**: En `sensor`-entitet.
* **Sensor för Laddboxens Dynamiska Strömgräns (`charger_dynamic_current_sensor_id`)**:
    * **Beskrivning**: Valfri. För att aktivera en optimering som minskar onödiga kommandon, välj här en sensor som visar den **nuvarande aktiva dynamiska strömgränsen** som är satt på laddaren. Om detta fält är konfigurerat, kommer integrationen bara att skicka ett nytt `set_dynamic...`-kommando om mål-strömmen skiljer sig från den nuvarande. Detta kan vara användbart om t.ex. Easee-integrationen tillhandahåller en sådan sensor.
    * **Krav**: En `sensor`-entitet.
* **Effektsensor för Elbilens Laddning (`ev_power_sensor_id`)**:
    * **Beskrivning**: Valfri. Välj en sensor som mäter den faktiska effekt som bilen för närvarande laddas med (i Watt eller kW). Används för att beräkna ackumulerad energi och kostnad för den aktuella laddningssessionen. Om denna sensor saknas kommer sessionsdata för energi och kostnad inte att uppdateras korrekt.
    * **Krav**: En `sensor`-entitet med `device_class: power`.
* **Sensor för Bilens Laddningsnivå (SoC) (`ev_soc_sensor_id`)**:
    * **Beskrivning**: Valfri. Välj en sensor som visar bilens aktuella laddningsnivå i procent (%). Används tillsammans med "Övre SoC-gräns för Laddning" för att stoppa laddning när önskad nivå är nådd.
    * **Krav**: En `sensor`-entitet med `device_class: battery`.
* **Övre SoC-gräns för Laddning (`target_soc_limit`)**:
    * **Beskrivning**: Valfri. Ange ett numeriskt värde (0-100%) som representerar den maximala laddningsnivån du vill att bilen ska nå via denna integrations smarta laddningsfunktioner. Kräver att "Sensor för Bilens Laddningsnivå (SoC)" också är konfigurerad. Om utelämnad, ignoreras SoC-kontroll.
    * **Krav**: Ett tal mellan 0 och 100.
* **Uppdateringsintervall (sekunder) (`scan_interval_seconds`)**:
    * **Beskrivning**: Hur ofta (i sekunder) integrationen ska hämta data och omvärdera laddningsbeslut, utöver de händelsestyrda uppdateringarna (t.ex. prisändringar). Ett kortare intervall ger snabbare reaktioner men kan öka systemlasten.
    * **Krav**: Ett tal mellan 10 och 3600. Standard är 30 sekunder.
* **Aktivera debug-loggning (`debug_logging_enabled`)**:
    * **Beskrivning**: Kryssa i denna ruta för att aktivera detaljerad debug-loggning för integrationen. Detta är användbart för felsökning. Ändringar här kräver en omstart av integrationen (sker automatiskt när du sparar alternativen) för att träda i kraft fullt ut. Loggarna skrivs till Home Assistants standardloggfil (`home-assistant.log`).
    * **Krav**: Boolean (avkryssad/ikryssad). Standard är avkryssad (False).

## 5. Entiteter Skapade av Integrationen
Integrationen skapar följande entiteter automatiskt, baserat på ditt konfigurations-ID:

* **Switch (`..._smart_charging_enabled`)**: "Avancerad Elbilsladdning Smart Laddning Aktiv"
    * Slår PÅ/AV den pris/tid-styrda smartladdningen.
* **Switch (`..._solar_charging_enabled`)**: "Avancerad Elbilsladdning Aktivera Solenergiladdning"
    * Slår PÅ/AV laddning med solenergiöverskott.
* **Number (`..._max_charging_price`)**: "Avancerad Elbilsladdning Max Elpris"
    * Ställer in det maximala spotpriset (kr/kWh) du är villig att betala för Pris/Tid-laddning.
* **Number (`..._solar_charging_buffer`)**: "Avancerad Elbilsladdning Solenergi Buffer"
    * Ställer in en buffert (Watt) som ska reserveras för husets övriga behov innan solenergiöverskott används för laddning. T.ex. om satt till 500W, måste solöverskottet vara minst 500W *plus* den minsta laddeffekten för att solenergiladdning ska starta.
* **Number (`..._min_solar_charge_current_a`)**: "Avancerad Elbilsladdning Minsta Laddström Solenergi"
    * Ställer in den minsta strömstyrka (Ampere) som bilen ska laddas med när solenergiladdning är aktiv. Detta för att undvika att laddningen startar och stoppar kontinuerligt vid små överskott. Måste vara minst 6A för de flesta laddboxar.
* **Sensor (`..._session_energy`)**: "Avancerad Elbilsladdning Session Energi"
    * Visar ackumulerad energi (kWh) för den pågående smarta laddningssessionen. Nollställs när en ny session startar.
* **Sensor (`..._session_cost`)**: "Avancerad Elbilsladdning Session Kostnad"
    * Visar den ackumulerade kostnaden (SEK, eller annan basvaluta beroende på prissensor) för den pågående smarta laddningssessionen (baserat på spotpris + ev. påslag, gäller primärt för Pris/Tid-läget). Nollställs när en ny session startar.
* **Sensor (`..._active_control_mode`)**: "Avancerad Elbilsladdning Aktivt Styrningsläge"
    * Visar det faktiska styrningsläget som för närvarande är aktivt och kontrollerar laddningen: "PRIS_TID", "SOLENERGI" eller "AV".

## 6. Kärnlogik och Styrningsstrategier
All styrningslogik hanteras av en central "koordinator" i integrationen. Den uppdateras både periodiskt (baserat på ditt inställda "Uppdateringsintervall") och omedelbart när viktiga sensorer ändrar tillstånd (t.ex. laddarstatus, elpris, solproduktion, SoC).

Detaljerad information om logiken finns i utvecklingsdokumentationen.

## 7. Felsökning
* **Kontrollera Loggarna**: Om något inte fungerar som förväntat, aktivera "debug-loggning" via integrationens alternativ och inspektera Home Assistants loggfil (`config/home-assistant.log`). Leta efter meddelanden från `custom_components.smart_ev_charging`.
* **Verifiera Entiteter**: Säkerställ att alla sensorer och hjälpare du konfigurerat i integrationen faktiskt existerar i Home Assistant och visar korrekta värden.
* **Easee-integrationen**: Se till att den grundläggande Easee-integrationen fungerar korrekt och att du kan styra laddaren manuellt via den.
* **Scheman**: Dubbelkolla att dina `schedule`-hjälpare är korrekt konfigurerade och är PÅ (aktiva) när du förväntar dig att laddning ska ske.
* **Starta Om**: Ibland kan en omstart av Home Assistant eller enbart en omladdning av integrationen (via integrationssidan) lösa tillfälliga problem.

För ytterligare support, överväg att skapa ett "Issue" på integrationens GitHub-sida (om tillgängligt).
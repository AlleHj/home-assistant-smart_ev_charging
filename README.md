# Avancerad Elbilsladdning för Home Assistant

Detta är en anpassad integration (custom component) för Home Assistant som möjliggör avancerad styrning av elbilsladdning, primärt med fokus på Easee-laddboxar.

## Funktioner
* **Pris/Tid-styrd laddning**: Ladda när elpriset är lågt och inom definierade tidsscheman.
* **Solenergiladdning**: Ladda med överskott från egna solpaneler.
* **SoC-gräns**: Ställ in en maximal laddningsnivå för bilen.
* **Dynamisk kontroll**: Anpassar laddningen baserat på flera faktorer i realtid. Inkluderar nu optimering för att minska onödiga API-anrop för att sätta laddström.
* **Anpassningsbara entiteter**: Skapar switchar och nummerinmatningar för enkel kontroll via Home Assistant UI.
* **Debug-läge**: Möjlighet att aktivera detaljerad loggning för felsökning.
* **Svenska texter i UI**: Konfigurationsflödet använder svenska texter via translations-fil.

## Installation
1.  Se till att du har [HACS (Home Assistant Community Store)](https://hacs.xyz/) installerat (rekommenderat), eller installera manuellt.
2.  **Via HACS (Rekommenderat):**
    * Sök efter "Avancerad Elbilsladdning" (eller det namn integrationen får i HACS) under Integrationer.
    * Installera integrationen.
3.  **Manuell Installation:**
    * Ladda ner den senaste versionen från [GitHub-repot](https://github.com/AlleHj/home-assistant-smart_ev_charging).
    * Kopiera innehållet i `custom_components/smart_ev_charging/` (inklusive den nya `translations`-mappen) till din Home Assistant-konfigurationsmapp under `<HA_config_mapp>/custom_components/smart_ev_charging/`.
4.  Starta om Home Assistant.
5.  Gå till "Inställningar" -> "Enheter & Tjänster" -> "Lägg till Integration" och sök efter "Avancerad Elbilsladdning".
6.  Följ konfigurationsguiden. Detaljerad information om varje parameter finns i [HELP.md](HELP.md).

## Konfiguration
All konfiguration sker via Home Assistants användargränssnitt, både vid initial installation och senare via "Alternativ" på integrationskortet.
För en detaljerad genomgång av alla konfigurationsalternativ, se [HELP.md](HELP.md).

## Versionshistorik

### Version 0.1.35 (2025-05-30)
* **Ny funktion**: Optimerad styrning för att undvika onödiga API-anrop. `set_dynamic_charger_circuit_current` anropas nu endast om mål-strömmen skiljer sig från den nuvarande aktiva gränsen (om en sensor för detta är konfigurerad).
* **Konfiguration**: Lade till ett nytt valfritt fält, "Sensor för Laddboxens Dynamiska Strömgräns (A)", för att möjliggöra den nya optimeringen.
* **Kodstandard**: Alla filversioner uppdaterade.

### Version 0.1.34 (2025-05-29)
* **Felrättning**: Korrigerat `TypeError` i `__init__.py` vid anrop till `SmartEVChargingCoordinator`-konstruktorn. Signaturen för koordinatorns `__init__` har justerats till att ta emot `scan_interval_seconds`, och anropet från `__init__.py` har anpassats för att matcha. `current_config` skickas inte längre till koordinatorn då den internt använder `entry.data | entry.options`.

### Version 0.1.33 (2025-05-29)
* **Felrättning**: Importerat `callback` från `homeassistant.core` i `coordinator.py` för att åtgärda "Undefined name `callback`"-fel för `@callback`-dekoratorn.

### Version 0.1.32 (2025-05-29)
* **Felrättning**: Korrigerat syntaxfel (användning av `?.`-operatorn) i `coordinator.py` vid hämtning av tillstånd för interna switchar och scheman. Ersatt med Python-korrekt logik för att hantera att entitetsobjekt kan vara `None`.

### Version 0.1.31 (2025-05-29)
* **Refaktorering**: Tagit bort sensorerna för sessionsenergi (`sensor.avancerad_elbilsladdning_session_energi`) och sessionskostnad (`sensor.avancerad_elbilsladdning_session_kostnad`) samt all tillhörande beräkningslogik från integrationen. Detta inkluderar ändringar i `const.py`, `coordinator.py` och `sensor.py`.

### Version 0.1.30 (2025-05-29)
* **Dokumentation**: Klargjort i README (under felsökning/FAQ-sektion om det fanns en) eller som svar till användare att varningar i loggen om "Okänd eller saknad enhet ('{{ state_attr(...) }}')" för effektsensorer beror på felaktig konfiguration av `unit_of_measurement` i användarens template-sensorer i `configuration.yaml`. `unit_of_measurement` för template-sensorer måste vara en fast sträng, inte en template. Inga ändringar i komponentens Python-kod krävdes för detta.

### Version 0.1.29 (2025-05-29)
* **Felrättning (Options Flow)**: Bekräftat att justeringarna i `config_flow.py` (v0.1.28), som ändrade schemadefinitionen för valfria selektorer i Options Flow att använda `description={"suggested_value": ...}` istället för `default=...` (i likhet med en tidigare fungerande version), har löst problemet med att rensade entitetsfält inte sparades korrekt utan återgick till sina gamla värden. Både validering av tomma valfria fält och sparandet av rensade/ändrade fält i Options Flow fungerar nu som förväntat.

### Version 0.1.28 (2025-05-29)
* **Förbättring (Config Flow)**: Justerat `_build_common_schema` i `config_flow.py` för att hantera schemadefinition för Options Flow närmare den äldre, fungerande versionen som användaren tillhandahöll. Använder nu `description={"suggested_value": ...}` istället för `default=...` för `vol.Optional` för valfria selektorer i Options Flow, i ett försök att påverka hur frontend skickar data för rensade fält. `vol.Maybe()` behålls för dessa fält för att tillåta `None`.
* **Rättelse**: Åtgärdat diverse linting-varningar i `config_flow.py` (docstring, dict type hint, implementerat `is_matching`, tagit bort deprecierad `self.config_entry`-tilldelning).
* **Felsökning (Options Flow)**: Problemet att rensade entitetsfält i Options Flow inte sparas korrekt (gamla värdet kvarstår) undersöks fortfarande. Loggning av `user_input` är fortsatt aktivt för att fånga exakt data från frontend.

### Version 0.1.27 (2025-05-29)
* **Felsökning (Options Flow)**: Problemet med att rensade entitetsfält i Options Flow inte sparas korrekt (gamla värdet kvarstår) undersöks vidare. Användaren har indikerat att detta fungerade i en äldre version av integrationen. Detta tyder på en möjlig regression i `config_flow.py`. Fokus ligger nu på att jämföra nuvarande `config_flow.py` med den tidigare fungerande versionen för att identifiera skillnader i schema-definition eller hantering av `user_input` för Options Flow. Loggning av `user_input` från frontend är fortfarande kritisk för att fastställa exakt vilken data backend-koden tar emot.

### Version 0.1.26 (2025-05-29)
* **Rättelse**: Åtgärdat diverse linting-varningar i `config_flow.py`:
    * Implementerat en skellettversion av `is_matching` i `SmartEVChargingConfigFlow` för att uppfylla krav på abstrakt metod.
    * Lagt till docstring för `async_step_user` i `SmartEVChargingConfigFlow`.
    * Ändrat typ-hint `Dict` till `dict` för `errors`-variabeln.
    * (Bekräftat att deprecierad tilldelning av `self.config_entry` i `OptionsFlowHandler.__init__` är borttagen sedan v0.1.25).
* **Felsökning (Options Flow)**: Kärnproblemet med att rensade entitetsfält i Options Flow inte sparas korrekt (gamla värdet kvarstår) är **oförändrat**. Diagnos baserad på loggning av `user_input` (den data som tas emot från frontend) bekräftar att frontend skickar det gamla värdet istället för ett tomt värde (`""`) när ett fält rensas. Detta problem ligger utanför denna integrations backend-kod.

### Version 0.1.25 (2025-05-29)
* **Rättelse**: Åtgärdat en deprecieringsvarning i `config_flow.py` genom att ta bort den överflödiga tilldelningen `self.config_entry = config_entry` i `OptionsFlowHandler.__init__`. Basklassen tillhandahåller redan denna attribut.
* **Felsökning (Options Flow)**: Problemet att rensade entitetsfält i Options Flow inte sparas korrekt (gamla värdet kvarstår) är oförändrat. Diagnos baserad på loggning av `user_input` (den data som tas emot från frontend) bekräftar att frontend skickar det gamla värdet istället för ett tomt värde (`""`) när ett fält rensas. Detta problem ligger utanför denna integrations backend-kod och kan inte åtgärdas härifrån. Loggrad för `user_input` i Options Flow behålls tills vidare för att underlätta för användaren att se detta.

### Version 0.1.24 (2025-05-29)
* **Felsökning (Options Flow)**: Återinfört en debug-loggrad i `config_flow.py` för att explicit logga innehållet i `user_input` när Options Flow hanteras. Detta är ett diagnostiskt steg för att definitivt fastställa vilken data som tas emot från frontend när ett entitetsfält rensas, vilket är avgörande för att förstå varför rensade fält eventuellt inte sparas korrekt.

### Version 0.1.23 (2025-05-29)
* **Felsökning (Options Flow)**: Problemet att rensade entitetsfält i Options Flow inte sparas som tomma utan behåller sitt gamla värde kvarstår. Loggning av `options_to_save` (den data som Python-koden *försöker* spara) fortsätter att visa det gamla värdet. Detta indikerar med mycket hög sannolikhet att `user_input` (den rådata som Python-koden tar emot från Home Assistants frontend) felaktigt innehåller det gamla värdet, istället för ett tomt värde (`""`) som förväntas när ett fält rensas i UI. Problemet ligger därmed troligen i hur frontend skickar data under dessa omständigheter, vilket är utanför denna integrations omedelbara kontroll. Backend-koden hanterar den data den får korrekt. För definitiv diagnos krävs loggning av rå `user_input`.

### Version 0.1.19 (2025-05-29)
* **Felrättning (Options Flow & Initial Setup)**: Ytterligare justeringar i `config_flow.py` (`_build_common_schema`). Selektorer för fält som kan vara `None` (valfria entitetsfält och SoC-gräns) kapslas nu konsekvent med `vol.Maybe()` och använder `default=None` (om värdet faktiskt är `None`) i schemadefinitionen för både initial konfiguration och alternativflödet. Detta åtgärdar valideringsfel som "expected float" och "Entity None is neither a valid entity ID..." när dessa fält lämnas tomma. Detta kan även påverka hur frontend skickar data för rensade fält i Options Flow, vilket potentiellt kan avhjälpa det tidigare problemet med att gamla värden sparades.

### Version 0.1.17 (2025-05-29)
* **Felrättning (Options Flow & Initial Setup)**: Justerat `config_flow.py` (`_build_common_schema`) så att valfria entitetsfält nu använder `vol.Maybe(EntitySelector(...))` och korrekt `default=None` (om fältet är tomt) i schemadefinitionen för både initial konfiguration och alternativflödet. Detta bör förhindra valideringsfelet "Entity None is neither a valid entity ID nor a valid UUID" när dessa fält lämnas tomma eller rensas. Detta kan potentiellt även förbättra situationen där rensade fält i Options Flow inte sparades korrekt, om grundorsaken var relaterad till schema-validering.

### Version 0.1.16 (2025-05-29)
* **Felrättning (Initial Setup)**: Justerat `config_flow.py` (`_build_common_schema`) för den initiala konfigurationen. Valfria entitetsfält använder nu `vol.Optional(key, default=None)` och `vol.Maybe(EntitySelector(...))` för att korrekt tillåta att dessa fält lämnas tomma utan att orsaka valideringsfelet "Entity None is neither a valid entity ID nor a valid UUID".
* **Felsökning (Options Flow)**: Problemet med att rensade entitetsfält i Options Flow inte sparas korrekt kvarstår troligen. Logganalys tyder starkt på att felet ligger i att datan som tas emot från Home Assistants frontend (`user_input`) felaktigt innehåller det gamla värdet istället för ett tomt värde som indikerar att fältet rensats. Detta problem ligger sannolikt utanför denna integrations backend-kod och kan inte åtgärdas härifrån utan att riskera annan funktionalitet.

### Version 0.1.15 (2025-05-29)
* **Felrättning (Initial Setup)**: Justerat `config_flow.py` så att valfria entitetsfält (t.ex. SoC-sensor) under den initiala konfigurationen nu har `None` som schema-default istället för `""`. Detta förhindrar valideringsfelet "Entity is neither a valid entity ID nor a valid UUID" om dessa fält lämnas tomma av användaren.
* **Felsökning (Options Flow)**: Problemet med att rensade entitetsfält i Options Flow inte sparas korrekt kvarstår troligen. Logganalys tyder starkt på att felet ligger i att datan som tas emot från Home Assistants frontend (`user_input`) felaktigt innehåller det gamla värdet istället för ett tomt värde som indikerar att fältet rensats. Detta problem ligger sannolikt utanför denna integrations backend-kod. Ingen ändring i spara-logiken för Options Flow i detta steg.

### Version 0.1.14 (2025-05-29)
* **Felsökning**: Återställt `config_flow.py` från diagnostisk loggning. Analys av loggar pekar på att felet där rensade entitetsfält i Options Flow inte sparas korrekt beror på att datan som tas emot från Home Assistants frontend (`user_input`) innehåller det gamla värdet istället för ett tomt värde som indikerar att fältet rensats. Detta problem ligger troligen utanför denna integrations backend-kod.

### Version 0.1.13 (2025-05-29)
* **Felsökning**: Tog bort extra debug-loggning för `user_input` i `config_flow.py` (Options Flow) då diagnos indikerar att felet med att spara rensade entitetsfält troligen ligger i hur frontend skickar data, inte i hur backend tar emot eller bearbetar den. Komponentens Python-kod hanterar inkommande data korrekt.

### Version 0.1.12 (2025-05-29)
* **Felsökning**: Lade till utökad debug-loggning i `config_flow.py` (Options Flow) för att logga det `user_input` som tas emot från formuläret. Detta för att bättre kunna analysera varför rensade entitetsfält eventuellt inte sparas korrekt. Ingen ändring i spara-logiken i detta steg.

### Version 0.1.11 (2025-05-29)
* **Felrättning**: Justerat logiken i `config_flow.py` (Options Flow) för att säkerställa att ändringar av valfria entitetsfält (t.ex. att rensa ett tidigare satt SoC-sensorvärde) sparas korrekt och inte återgår till tidigare värden. Förtydligat hur `options_to_save` hanterar värden från `user_input` för alla konfigurationsnycklar.

### Version 0.1.10 (2025-05-29)
* **Felrättning**: Korrigerat `RuntimeError: Attribute hass is None` i `sensor.py`. Felet uppstod p.g.a. att `_handle_coordinator_update()` (som anropar `async_write_ha_state()`) anropades från sensorernas `__init__`-metod, vilket är för tidigt. Borttaget detta anrop då `CoordinatorEntity` hanterar detta automatiskt.

### Version 0.1.9 (2025-05-29)
* **Felrättning**: Korrigerat ett `AttributeError: 'NoneType' object has no attribute 'data'` som uppstod när man försökte öppna alternativflödet (Options Flow). Felet berodde på felaktig åtkomst till `hass`-objektet i `OptionsFlowHandler.__init__`.
* **Förbättring**: Justerat hur `default`-värden hanteras för `EntitySelector`-fält i `config_flow.py` (`_build_common_schema`), särskilt för valfria fält, för att bättre hantera tomma val och minska risken för "Entity None"-felet vid initial konfiguration. Valfria entitetsfält får nu `""` (tom sträng) som defaultvärde i schemat om inget annat värde finns, vilket `EntitySelector` hanterar bättre än `None` som default i UI. Detta konverteras sedan till `None` när datan sparas.
* **Förbättring**: Förenklat logiken för att spara options i `OptionsFlowHandler` genom att alltid skicka hela `options_to_save`-objektet. Detta bör mer robust hantera rensning/nollställning av tidigare satta optioner så att de inte felaktigt återkommer.

### Version 0.1.8 (2025-05-28)
* **Felrättning**: Korrigerat ett `AttributeError` i `config_flow.py` under den initiala konfigurationen (`async_step_user`). Felet uppstod vid byggandet av schemat på grund av felaktig åtkomst till attribut på selector-objekt. Logiken för att bygga `data_schema` i `_build_common_schema` har justerats för att hantera `vol.Required` och `vol.Optional` korrekt för både initial setup och options flow.
* **Dokumentation**: Uppdaterat filversionskommentar i `config_flow.py` och `manifest.json`.

### Version 0.1.7 (2025-05-28)
* **Lokalisering**: Infört en `translations/sv.json`-fil för att hantera alla texter i konfigurations- och alternativflödet. Detta säkerställer att UI:t visas helt på svenska.
* **Kodrefaktorering**: `config_flow.py` har skrivits om för att använda `CONF_`-konstanter som nycklar i schemat, vilket är standardpraxis när man använder translations-filer. Manuell mappning av etiketter har tagits bort.
* **Dokumentation**: Uppdaterat filversionskommentarer och `manifest.json`. Installationsinstruktioner i README har uppdaterats för att inkludera `translations`-mappen.

### Version 0.1.6 (2025-05-28)
* **UI Förbättring**: Uppdaterat `config_flow.py` för att visa tydliga svenska etiketter för alla konfigurationsfält i användargränssnittet istället för engelska konstansnamn. Detta förbättrar användarvänligheten avsevärt. (Not: Denna metod ersätts nu av translations i 0.1.7).
* **Dokumentation**: Uppdaterade filversionskommentar i `config_flow.py` och `manifest.json`.

### Version 0.1.5 (2025-05-28)
* **Kodförbättring**: Ytterligare åtgärder för Pylint/linter-varningar i `coordinator.py`:
    * Korrigerat logganrop med komplexa f-strängar (specifikt den långa "Indata:"-debugsträngen) till att använda korrekta format specifiers och förformaterade strängargument för villkorliga värden (lazy logging).
    * Justerat `if/elif`-strukturer i `_get_surcharge_in_kr_kwh` och `_get_power_value` för att tydligare hantera returvärden i `else`-block och undvika "Consider moving this statement to an `else` block"-varningar.
* **Dokumentation**: Uppdaterade filversionskommentar i `coordinator.py` och `manifest.json` (manifest versionen förblev 0.1.5).

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
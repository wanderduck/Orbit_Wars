# Orbit Wars: Kaggle Competition Overview and Rules

This Markdown document contains two main sections:
1. Orbit Wars: Kaggle Competition Overview
2. Orbit Wars: Kaggle Competition Rules

The first section (heading: “Orbit Wars: Kaggle Competition Overview”) provides a brief overview of the Kaggle Competition, the main goal to be achieved, the basics of the Orbit Wars game, the prizes for placing in the top 10, scoring and other game information, et cetera.

The second section (heading: “Orbit Wars Kaggle Competition Rules”) provides an in-depth explanation of all the rules that apply specifically to this Kaggle competition.

The sections are separated by three (3) horizontal bars and are denoted by a level-one headings (i.e. level-one headings that are after this level-one heading).

---

# Orbit Wars: Kaggle Competition Overview

## Overview

The goal of this competition is to create and/or train AI bots to play a novel multi-agent 1v1 or 4p FFA game against other submitted agents.

## Description

**Welcome to Orbit Wars!** Command the fleet. Conquer the void. Orbit Wars resurrects the ruthless strategy of the 2010 Planet Wars challenge with fresh, exciting mechanics. Launch massive swarms of ships across the solar system, outmaneuver your enemies, and claim absolute orbital supremacy.

## Evaluation

Each day your team is able to submit up to 5 agents (bots) to the competition. Each submission will play Episodes (games) against other bots on the ladder that have a similar skill rating. Over time skill ratings will go up with wins or down with losses and evened out with ties. To reduce the number of bots playing and increase the number of episodes each team participates in, we only track the latest 2 submissions and use those for final submissions.

Every bot submitted will continue to play episodes until the end of the competition, with newer bots playing a much more frequent number of episodes. On the leaderboard, only your best scoring bot will be shown, but you can track the progress of all of your submissions on your Submissions page.

Each Submission has an estimated Skill Rating which is modeled by a Gaussian N(μ,σ2) where μ is the estimated skill and σ represents the uncertainty of that estimate which will decrease over time.

When you upload a Submission, we first play a Validation Episode where that Submission plays against copies of itself to make sure it works properly. If the Episode fails, the Submission is marked as Error and you can download the agent logs to help figure out why. Otherwise, we initialize the Submission with μ0=600 and it joins the pool of All Submissions for ongoing evaluation.

We repeatedly run Episodes from the pool of All Submissions, and try to pick Submissions with similar ratings for fair matches. Newly submitted agents will be given an increased rate in the number of episodes run to give you faster feedback.

**Ranking System**

After an Episode finishes, we'll update the Rating estimate for all Submissions in that Episode. If one Submission won, we'll increase its μ and decrease its opponent's μ -- if the result was a draw, then we'll move the two μ values closer towards their mean. The updates will have magnitude relative to the deviation from the expected result based on the previous μ values, and also relative to each Submission's uncertainty σ. We also reduce the σ terms relative to the amount of information gained by the result. The score by which your bot wins or loses an Episode does not affect the skill rating updates.

**Final Evaluation** At the submission deadline on June 23, 2026, additional submissions will be locked. From June 23, 2026 for approximately two weeks, we will continue to run games. At the conclusion of this period, the leaderboard is final.

## Timeline

- **April 16, 2026** - Start Date.
    
- **June 16, 2026** - Entry Deadline. You must accept the competition rules before this date in order to compete.
    
- **June 16, 2026** - Team Merger Deadline. This is the last day participants may join or merge teams.
    
- **June 23, 2026** - Final Submission Deadline.
    
- **June 24, 2026 to (approx) July 8, 2026** - We will continue to run games, or until the leaderboard has reached convergence. At the conclusion of this period, the leaderboard is final.
    

All deadlines are at 11:59 PM UTC on the corresponding day unless otherwise noted. _The competition organizers reserve the right to update the contest timeline if they deem it necessary._

## Prizes

- 1st Place - $5,000
- 2nd Place - $5,000
- 3rd Place - $5,000
- 4th Place - $5,000
- 5th Place - $5,000
- 6th Place - $5,000
- 7th Place - $5,000
- 8th Place - $5,000
- 9th Place - $5,000
- 10th Place - $5,000

## Getting Started

All instructions in addition to the starter kits you need to start writing a bot and submit them to the competition are in the [starter kit](https://kaggle.com/competitions/orbit-wars/code).

Make sure to also read the competition specs below to learn how this year’s design works!

### How to Play Orbit Wars

#### Overview

Players start with a single home planet and compete to control the map by sending fleets to capture neutral and enemy planets. The board is a 100x100 continuous space with a sun at the center. Planets orbit the sun, comets fly through on elliptical trajectories, and fleets travel in straight lines. The game lasts 500 turns. The player with the most total ships (on planets + in fleets) at the end wins.

#### Board Layout

- **Board**: 100x100 continuous space, origin at top-left.
- **Sun**: Centered at (50, 50) with radius 10. Fleets that cross the sun are destroyed.
- **Symmetry**: All planets and comets are placed with 4-fold mirror symmetry around the center: `(x, y), (100-x, y), (x, 100-y), (100-x, 100-y)`. This ensures fairness regardless of starting position.

#### Planets

Each planet is represented as `[id, owner, x, y, radius, ships, production]`.

- **owner**: Player ID (0-3), or -1 for neutral.
- **radius**: Determined by production: `1 + ln(production)`. Higher production planets are physically larger.
- **production**: Integer from 1 to 5. Each turn, an owned planet generates this many ships.
- **ships**: Current garrison. Starts between 5 and 99 (skewed toward lower values).

##### Planet Types

- **Orbiting planets**: Planets whose `orbital_radius + planet_radius < 50` rotate around the sun at a constant angular velocity (0.025-0.05 radians/turn, randomized per game). Use `initial_planets` and `angular_velocity` from the observation to predict their positions.
- **Static planets**: Planets further from the center do not rotate.

The map contains 20-40 planets (5-10 symmetric groups of 4). At least 3 groups are guaranteed to be static, and at least one group is guaranteed to be orbiting.

##### Home Planets

One symmetric group is randomly chosen as the starting planets. In a 2-player game, players start on diagonally opposite planets (Q1 and Q4). In a 4-player game, each player gets one planet from the group. Home planets start with 10 ships.

#### Fleets

Each fleet is represented as `[id, owner, x, y, angle, from_planet_id, ships]`.

- **angle**: Direction of travel in radians.
- **ships**: Number of ships in the fleet (does not change during travel).

##### Fleet Speed

Fleet speed scales with size on a logarithmic curve:

```apache
speed = 1.0 + (maxSpeed - 1.0) * (log(ships) / log(1000)) ^ 1.5
```

- 1 ship moves at 1.0 units/turn.
- Larger fleets move faster, approaching the maximum speed (default 6.0).
- A fleet of ~500 ships moves at ~5, and ~1000 ships reaches the max.

##### Fleet Movement

Fleets travel in a straight line at their computed speed each turn. A fleet is removed if it:

- Goes out of bounds (leaves the 100x100 playing field).
- Crosses the sun (path segment comes within the sun's radius).
- Collides with any planet (path segment comes within the planet's radius). This triggers combat.

Collision detection is continuous -- the entire path segment from old to new position is checked, not just the endpoint.

##### Fleet Launch

Each turn, your agent returns a list of moves: `[from_planet_id, direction_angle, num_ships]`.

- You can only launch from planets you own.
- You cannot launch more ships than the planet currently has.
- The fleet spawns just outside the planet's radius in the given direction.
- You can issue multiple launches from the same or different planets in a single turn.

#### Comets

Comets are temporary extra-solar objects that fly through the board on highly elliptical orbits around the sun. They spawn in groups of 4 (one per quadrant) at steps 50, 150, 250, 350, and 450.

- **Radius**: 1.0 (fixed).
- **Production**: 1 ship/turn when owned.
- **Starting ships**: Random, skewed low (minimum of 4 rolls from 1-99). All 4 comets in a group share the same starting ship count.
- **Speed**: Configurable via `cometSpeed` (default 4.0 units/turn).
- **Identification**: Check `comet_planet_ids` in the observation to see which planet IDs are comets. Comets also appear in the `planets` array and follow all normal planet rules (capture, production, fleet launch, combat).

When a comet leaves the board, it is removed along with any ships garrisoned on it. Comets are removed before fleet launches each turn, so you cannot launch from a departing comet.

The `comets` observation field contains comet group data including `paths` (the full trajectory for each comet) and `path_index` (current position along the path), which can be used to predict future comet positions.

#### Turn Order

Each turn executes in this order:

1. **Comet expiration**: Remove comets that have left the board.
2. **Comet spawning**: Spawn new comet groups at designated steps.
3. **Fleet launch**: Process all player actions, creating new fleets.
4. **Production**: All owned planets (including comets) generate ships.
5. **Fleet movement**: Move all fleets along their headings. Check for out-of-bounds, sun collision, and planet collision. Fleets that hit planets are queued for combat.
6. **Planet rotation & comet movement**: Orbiting planets rotate, comets advance along their paths. Any fleet caught by a moving planet/comet is swept into combat with it.
7. **Combat resolution**: Resolve all queued planet combats.

#### Combat

When one or more fleets collide with a planet (either by flying into it or being swept by a moving planet), combat is resolved:

1. All arriving fleets are grouped by owner. Ships from the same owner are summed.
2. The largest attacking force fights the second largest. The difference in ships survives.
3. If there is a surviving attacker:
    - If the attacker is the same owner as the planet, the surviving ships are added to the garrison.
    - If the attacker is a different owner, the surviving ships fight the garrison. If the attackers exceed the garrison, the planet changes ownership and the garrison becomes the surplus.
4. If two attackers tie, all attacking ships are destroyed (no survivors).

#### Scoring and Termination

The game ends when:

- **Step limit reached**: 500 turns.
- **Elimination**: Only one player (or zero) remains with any planets or fleets.

Final score = total ships on owned planets + total ships in owned fleets. Highest score wins.

### Observation Reference

|Field|Type|Description|
|---|---|---|
|`planets`|`[[id, owner, x, y, radius, ships, production], ...]`|All planets including comets|
|`fleets`|`[[id, owner, x, y, angle, from_planet_id, ships], ...]`|All active fleets|
|`player`|`int`|Your player ID (0-3)|
|`angular_velocity`|`float`|Planet rotation speed (radians/turn)|
|`initial_planets`|`[[id, owner, x, y, radius, ships, production], ...]`|Planet positions at game start|
|`comets`|`[{planet_ids, paths, path_index}, ...]`|Active comet group data|
|`comet_planet_ids`|`[int, ...]`|Planet IDs that are comets|
|`remainingOverageTime`|`float`|Remaining overage time budget (seconds)|

### Action Format

Return a list of moves:

```inform7
[[from_planet_id, direction_angle, num_ships], ...]
```

- `from_planet_id`: ID of a planet you own.
- `direction_angle`: Angle in radians (0 = right, pi/2 = down).
- `num_ships`: Integer number of ships to send.

Return an empty list `[]` to take no action.

### Agent Convenience

The module exports named tuples for easier field access:

```routeros
from kaggle_environments.envs.orbit_wars.orbit_wars import Planet, Fleet, CENTER, ROTATION_RADIUS_LIMIT

def agent(obs):
    planets = [Planet(*p) for p in obs.get("planets", [])]
    fleets = [Fleet(*f) for f in obs.get("fleets", [])]
    player = obs.get("player", 0)

    for p in planets:
        print(p.id, p.owner, p.x, p.y, p.radius, p.ships, p.production)

    return []  # list of [from_planet_id, angle, num_ships]
```

### Configuration

| Parameter      | Default | Description              |
| -------------- | ------- | ------------------------ |
| `episodeSteps` | 500     | Maximum number of turns  |
| `actTimeout`   | 1       | Seconds per turn         |
| `shipSpeed`    | 6.0     | Maximum fleet speed      |
| `sunRadius`    | 10.0    | Radius of the sun        |
| `boardSize`    | 100.0   | Board dimensions         |
| `cometSpeed`   | 4.0     | Comet speed (units/turn) |



---
---
---



# Orbit Wars: Kaggle Competition Rules

## Competition Rules

## ENTRY IN THIS COMPETITION CONSTITUTES YOUR ACCEPTANCE OF THESE OFFICIAL COMPETITION RULES.

**[See Section 3.18 for defined terms](https://www.kaggle.com/competitions/orbit-wars/rules#18.-terms)**

_The Competition named below is a skills-based competition to promote and further the field of data science. You must register via the Competition Website to enter. To enter the Competition, you must agree to these Official Competition Rules, which incorporate by reference the provisions and content of the Competition Website and any Specific Competition Rules herein (collectively, the "Rules"). Please read these Rules carefully before entry to ensure you understand and agree. You further agree that Submission in the Competition constitutes agreement to these Rules. You may not submit to the Competition and are not eligible to receive the prizes associated with this Competition unless you agree to these Rules. These Rules form a binding legal agreement between you and the Competition Sponsor with respect to the Competition. Your competition Submissions must conform to the requirements stated on the Competition Website. Your Submissions will be scored based on the evaluation metric described on the Competition Website. Subject to compliance with the Competition Rules, Prizes, if any, will be awarded to Participants with the best scores, based on the merits of the data science models submitted. See below for the complete Competition Rules. For Competitions designated as hackathons by the Competition Sponsor (“Hackathons”), your Submissions will be judged by the Competition Sponsor based on the evaluation rubric set forth on the Competition Website (“Evaluation Rubric”). The Prizes, if any, will be awarded to Participants with the highest ranking(s) as determined by the Competition Sponsor based on such rubric._

**You cannot sign up to Kaggle from multiple accounts and therefore you cannot enter or submit from multiple accounts.**

### 1. COMPETITION-SPECIFIC TERMS

#### 1. COMPETITION TITLE

Orbit Wars

#### 2. COMPETITION SPONSOR

Google LLC

#### 3. COMPETITION SPONSOR ADDRESS

1600 Amphitheatre Parkway, Mountain View, CA 94043

#### 4. COMPETITION WEBSITE

[https://www.kaggle.com/competitions/orbit-wars](https://www.kaggle.com/competitions/orbit-wars)

#### 5. TOTAL PRIZES AVAILABLE: $50,000

- First Prize: $5,000
- Second Prize: $5,000
- Third Prize: $5,000
- Fourth Prize: $5,000
- Fifth Prize: $5,000
- Sixth Prize: $5,000
- Seventh Prize: $5,000
- Eighth Prize: $5,000
- Ninth Prize: $5,000
- Tenth Prize: $5,000

#### 6. WINNER LICENSE TYPE

CC-BY 4.0

#### 7. DATA ACCESS AND USE

Apache 2.0

### 2. COMPETITION-SPECIFIC RULES

In addition to the provisions of the General Competition Rules below, you understand and agree to these Competition-Specific Rules required by the Competition Sponsor:

#### 1. TEAM LIMITS

a. The maximum Team size is five (5). b. Team mergers are allowed and can be performed by the Team leader. In order to merge, the combined Team must have a total Submission count less than or equal to the maximum allowed as of the Team Merger Deadline. The maximum allowed is the number of Submissions per day multiplied by the number of days the competition has been running. For Hackathons, each team is allowed one (1) Submission; any Submissions submitted by Participants before merging into a Team will be unsubmitted.

#### 2. SUBMISSION LIMITS

a. You may submit a maximum of five (5) Submissions per day. b. You may select up to two (2) Final Submissions for judging. c. For Hackathons, each Team may submit one (1) Submission only.

#### 3. COMPETITION TIMELINE

a. Competition Timeline dates (including Entry Deadline, Final Submission Deadline, Start Date, and Team Merger Deadline, as applicable) are reflected on the competition’s Overview > Timeline page.

#### 4. COMPETITION DATA

a. Data Access and Use.

1. You may access and use the Competition Data for any purpose, whether commercial or non-commercial, including for participating in the Competition and on Kaggle.com forums, and for academic research and education. The Competition Sponsor reserves the right to disqualify any Participant who uses the Competition Data other than as permitted by the Competition Website and these Rules.
    
2. The Competition Data is also subject to the following terms and conditions: [Apache 2.0](https://www.apache.org/licenses/LICENSE-2.0).
    

b. Data Security.

1. You agree to use reasonable and suitable measures to prevent persons who have not formally agreed to these Rules from gaining access to the Competition Data. You agree not to transmit, duplicate, publish, redistribute or otherwise provide or make available the Competition Data to any party not participating in the Competition. You agree to notify Kaggle immediately upon learning of any possible unauthorized transmission of or unauthorized access to the Competition Data and agree to work with Kaggle to rectify any unauthorized transmission or access.

#### 5. WINNER LICENSE

a. Under Section 2.8 (Winners Obligations) of the General Rules below, you hereby grant and will grant the Competition Sponsor the following license(s) with respect to your Submission if you are a Competition winner:

1. You hereby license and will license your winning Submission and the source code used to generate the Submission under [CC-BY 4.0](https://creativecommons.org/licenses/by/4.0/deed.en)
    
2. For generally commercially available software that you used to generate your Submission that is not owned by you, but that can be procured by the Competition Sponsor without undue expense, you do not need to grant the license in the preceding Section for that software.
    
3. In the event that input data or pretrained models with an incompatible license are used to generate your winning solution, you do not need to grant an open source license in the preceding Section for that data and/or model(s).
    

b. You may be required by the Sponsor to provide a detailed description of how the winning Submission was generated, to the Competition Sponsor’s specifications, as outlined in Section 2.8, Winner’s Obligations. This may include a detailed description of methodology, where one must be able to reproduce the approach by reading the description, and includes a detailed explanation of the architecture, preprocessing, loss function, training details, hyper-parameters, etc. The description should also include a link to a code repository with complete and detailed instructions so that the results obtained can be reproduced.

#### 6. EXTERNAL DATA AND TOOLS

a. You may use data other than the Competition Data (“External Data”) to develop and test your Submissions. However, you will ensure the External Data is either publicly available and equally accessible to use by all Participants of the Competition for purposes of the competition at no cost to the other Participants, or satisfies the Reasonableness criteria as outlined in Section 2.6.b below. The ability to use External Data under this Section does not limit your other obligations under these Competition Rules, including but not limited to Section 2.8 (Winners Obligations).

b. The use of external data and models is acceptable unless specifically prohibited by the Host. Because of the potential costs or restrictions (e.g., “geo restrictions”) associated with obtaining rights to use external data or certain software and associated tools, their use must be “reasonably accessible to all” and of “minimal cost”. Also, regardless of the cost challenges as they might affect all Participants during the course of the competition, the costs of potentially procuring a license for software used to generate a Submission, must also be considered. The Host will employ an assessment of whether or not the following criteria can exclude the use of the particular LLM, data set(s), or tool(s):

1. Are Participants being excluded from a competition because of the "excessive" costs for access to certain LLMs, external data, or tools that might be used by other Participants. The Host will assess the excessive cost concern by applying a “Reasonableness” standard (the “Reasonableness Standard”). The Reasonableness Standard will be determined and applied by the Host in light of things like cost thresholds and accessibility.
    
2. By way of example only, a small subscription charge to use additional elements of a large language model such as Gemini Advanced are acceptable if meeting the Reasonableness Standard of Sec. 8.2. Purchasing a license to use a proprietary dataset that exceeds the cost of a prize in the competition would not be considered reasonable.
    

c. Automated Machine Learning Tools (“AMLT”)

1. Individual Participants and Teams may use automated machine learning tool(s) (“AMLT”) (e.g., Google toML, H2O Driverless AI, etc.) to create a Submission, provided that the Participant or Team ensures that they have an appropriate license to the AMLT such that they are able to comply with the Competition Rules.

#### 7. ELIGIBILITY

a. Unless otherwise stated in the Competition-Specific Rules above or prohibited by internal policies of the Competition Entities, employees, interns, contractors, officers and directors of Competition Entities may enter and participate in the Competition, but are not eligible to win any Prizes. "Competition Entities" means the Competition Sponsor, Kaggle Inc., and their respective parent companies, subsidiaries and affiliates. If you are such a Participant from a Competition Entity, you are subject to all applicable internal policies of your employer with respect to your participation.

#### 8. WINNER’S OBLIGATIONS

a. As a condition to being awarded a Prize, a Prize winner must fulfill the following obligations:

1. Provide a detailed description of how the winning Submission was generated in the Competition forums, to the Competition Sponsor’s specifications. This may include a detailed description of methodology, where one must be able to reproduce the approach by reading the description, and includes a detailed explanation of the architecture, preprocessing, loss function, training details, hyper-parameters, etc. The description should also include a link to a code repository with complete and detailed instructions so that the results obtained can be reproduced.

a. To the extent that the final model’s software code includes generally commercially available software that is not owned by you, but that can be procured by the Competition Sponsor without undue expense, then instead of delivering the code for that software to the Competition Sponsor, you must identify that software, method for procuring it, and any parameters or other information necessary to replicate the winning Submission; Individual Participants and Teams who create a Submission using an AMLT may win a Prize. However, for clarity, the potential winner’s Submission must still meet the requirements of these Rules, including but not limited to Section 2.5 (Winners License), Section 2.8 (Winners Obligations), and Section 3.14 (Warranty, Indemnity, and Release).”

b. Individual Participants and Teams who create a Submission using an AMLT may win a Prize. However, for clarity, the potential winner’s Submission must still meet the requirements of these Rules,

1. Grant to the Competition Sponsor the license to the winning Submission stated in the Competition Specific Rules above, and represent that you have the unrestricted right to grant that license;
    
2. Sign and return all Prize acceptance documents as may be required by Competition Sponsor or Kaggle, including without limitation: (a) eligibility certifications; (b) licenses, releases and other agreements required under the Rules; and (c) U.S. tax forms (such as IRS Form W-9 if U.S. resident, IRS Form W-8BEN if foreign resident, or future equivalents).
    

#### 9. GOVERNING LAW

a. Unless otherwise provided in the Competition Specific Rules above, all claims arising out of or relating to these Rules will be governed by California law, excluding its conflict of laws rules, and will be litigated exclusively in the Federal or State courts of Santa Clara County, California, USA. The parties consent to personal jurisdiction in those courts. If any provision of these Rules is held to be invalid or unenforceable, all remaining provisions of the Rules will remain in full force and effect.

#### **10. SCORING AND LEADERBOARD**

Your Submissions will be scored based on their performance in an episode, and your performances in episodes will be aggregated to determine your position on the Leaderboard, in each case as described in the evaluation documentation on the Competition Website. There is no Private Leaderboard in Simulation competitions.

#### **11. ENVIRONMENTS & PUBLIC AVAILABILITY**

This Competition makes use of Kaggle Environments. Additional rules related to the Environment(s) used in this Competition are available on the Competition Website. A replay of each episode of the competition, which includes the actions taken by your Submission in the episode, may be publicly available and downloadable.

#### **12. NO INGRESS OR EGRESS**

During the evaluation of an episode your Submission may not pull in or use any information external to the Submission and Environment and may not send any information out.

### 3. GENERAL COMPETITION RULES - BINDING AGREEMENT

#### 1. ELIGIBILITY

a. To be eligible to enter the Competition, you must be:

1. a registered account holder at Kaggle.com;
2. the older of 18 years old or the age of majority in your jurisdiction of residence (unless otherwise agreed to by Competition Sponsor and appropriate parental/guardian consents have been obtained by Competition Sponsor);
3. not a resident of Crimea, so-called Donetsk People's Republic (DNR) or Luhansk People's Republic (LNR), Cuba, Iran, or North Korea; and
4. not a person or representative of an entity under U.S. export controls or sanctions (see: [https://www.treasury.gov/resourcecenter/sanctions/Programs/Pages/Programs.aspx](https://www.treasury.gov/resource-center/sanctions/Programs/Pages/Programs.aspx)).

b. Competitions are open to residents of the United States and worldwide, except that if you are a resident of Crimea, so-called Donetsk People's Republic (DNR) or Luhansk People's Republic (LNR), Cuba, Iran, North Korea, or are subject to U.S. export controls or sanctions, you may not enter the Competition. Other local rules and regulations may apply to you, so please check your local laws to ensure that you are eligible to participate in skills-based competitions. The Competition Host reserves the right to forego or award alternative Prizes where needed to comply with local laws. If a winner is located in a country where prizes cannot be awarded, then they are not eligible to receive a prize.

c. If you are entering as a representative of a company, educational institution or other legal entity, or on behalf of your employer, these rules are binding on you, individually, and the entity you represent or where you are an employee. If you are acting within the scope of your employment, or as an agent of another party, you warrant that such party or your employer has full knowledge of your actions and has consented thereto, including your potential receipt of a Prize. You further warrant that your actions do not violate your employer's or entity's policies and procedures.

d. The Competition Sponsor reserves the right to verify eligibility and to adjudicate on any dispute at any time. If you provide any false information relating to the Competition concerning your identity, residency, mailing address, telephone number, email address, ownership of right, or information required for entering the Competition, you may be immediately disqualified from the Competition.

#### 2. SPONSOR AND HOSTING PLATFORM

a. The Competition is sponsored by Competition Sponsor named above. The Competition is hosted on behalf of Competition Sponsor by Kaggle Inc. ("Kaggle"). Kaggle is an independent contractor of Competition Sponsor, and is not a party to this or any agreement between you and Competition Sponsor. You understand that Kaggle has no responsibility with respect to selecting the potential Competition winner(s) or awarding any Prizes. Kaggle will perform certain administrative functions relating to hosting the Competition, and you agree to abide by the provisions relating to Kaggle under these Rules. As a Kaggle.com account holder and user of the Kaggle competition platform, remember you have accepted and are subject to the Kaggle Terms of Service at [www.kaggle.com/terms](http://www.kaggle.com/terms) in addition to these Rules.

#### 3. COMPETITION PERIOD

a. For the purposes of Prizes, the Competition will run from the Start Date and time to the Final Submission Deadline (such duration the “Competition Period”). The Competition Timeline is subject to change, and Competition Sponsor may introduce additional hurdle deadlines during the Competition Period. Any updated or additional deadlines will be publicized on the Competition Website. It is your responsibility to check the Competition Website regularly to stay informed of any deadline changes. YOU ARE RESPONSIBLE FOR DETERMINING THE CORRESPONDING TIME ZONE IN YOUR LOCATION.

#### 4. COMPETITION ENTRY

a. NO PURCHASE NECESSARY TO ENTER OR WIN. To enter the Competition, you must register on the Competition Website prior to the Entry Deadline, and follow the instructions for developing and entering your Submission through the Competition Website. Your Submissions must be made in the manner and format, and in compliance with all other requirements, stated on the Competition Website (the "Requirements"). Submissions must be received before any Submission deadlines stated on the Competition Website. Submissions not received by the stated deadlines will not be eligible to receive a Prize. b. Except as expressly allowed in Hackathons as set forth on the Competition Website, submissions may not use or incorporate information from hand labeling or human prediction of the validation dataset or test data records. c. If the Competition is a multi-stage competition with temporally separate training and/or test data, one or more valid Submissions may be required during each Competition stage in the manner described on the Competition Website in order for the Submissions to be Prize eligible. d. Submissions are void if they are in whole or part illegible, incomplete, damaged, altered, counterfeit, obtained through fraud, or late. Competition Sponsor reserves the right to disqualify any entrant who does not follow these Rules, including making a Submission that does not meet the Requirements.

#### 5. INDIVIDUALS AND TEAMS

a. Individual Account. You may make Submissions only under one, unique Kaggle.com account. You will be disqualified if you make Submissions through more than one Kaggle account, or attempt to falsify an account to act as your proxy. You may submit up to the maximum number of Submissions per day as specified on the Competition Website. b. Teams. If permitted under the Competition Website guidelines, multiple individuals may collaborate as a Team; however, you may join or form only one Team. Each Team member must be a single individual with a separate Kaggle account. You must register individually for the Competition before joining a Team. You must confirm your Team membership to make it official by responding to the Team notification message sent to your Kaggle account. Team membership may not exceed the Maximum Team Size stated on the Competition Website. c. Team Merger. Teams (or individual Participants) may request to merge via the Competition Website. Team mergers may be allowed provided that: (i) the combined Team does not exceed the Maximum Team Size; (ii) the number of Submissions made by the merging Teams does not exceed the number of Submissions permissible for one Team at the date of the merger request; (iii) the merger is completed before the earlier of: any merger deadline or the Competition deadline; and (iv) the proposed combined Team otherwise meets all the requirements of these Rules. d. Private Sharing. No private sharing outside of Teams. Privately sharing code or data outside of Teams is not permitted. It's okay to share code if made available to all Participants on the forums.

#### 6. SUBMISSION CODE REQUIREMENTS

a. Private Code Sharing. Unless otherwise specifically permitted under the Competition Website or Competition Specific Rules above, during the Competition Period, you are not allowed to privately share source or executable code developed in connection with or based upon the Competition Data or other source or executable code relevant to the Competition (“Competition Code”). This prohibition includes sharing Competition Code between separate Teams, unless a Team merger occurs. Any such sharing of Competition Code is a breach of these Competition Rules and may result in disqualification. b. Public Code Sharing. You are permitted to publicly share Competition Code, provided that such public sharing does not violate the intellectual property rights of any third party. If you do choose to share Competition Code or other such code, you are required to share it on Kaggle.com on the discussion forum or notebooks associated specifically with the Competition for the benefit of all competitors. By so sharing, you are deemed to have licensed the shared code under an Open Source Initiative-approved license (see [www.opensource.org](http://www.opensource.org/)) that in no event limits commercial use of such Competition Code or model containing or depending on such Competition Code. c. Use of Open Source. Unless otherwise stated in the Specific Competition Rules above, if open source code is used in the model to generate the Submission, then you must only use open source code licensed under an Open Source Initiative-approved license (see [www.opensource.org](http://www.opensource.org/)) that in no event limits commercial use of such code or model containing or depending on such code.

#### 7. DETERMINING WINNERS

a. Each Submission will be scored and/or ranked by the evaluation metric, or Evaluation Rubric (in the case of Hackathon Competitions),stated on the Competition Website. During the Competition Period, the current ranking will be visible on the Competition Website's Public Leaderboard. The potential winner(s) are determined solely by the leaderboard ranking on the Private Leaderboard, subject to compliance with these Rules. The Public Leaderboard will be based on the public test set and the Private Leaderboard will be based on the private test set. There will be no leaderboards for Hackathon Competitions. b. In the event of a tie, the Submission that was entered first to the Competition will be the winner. In the event a potential winner is disqualified for any reason, the Submission that received the next highest score rank will be chosen as the potential winner. For Hackathon Competitions, each of the top Submissions will get a unique ranking and there will be no tiebreakers.

#### 8. NOTIFICATION OF WINNERS & DISQUALIFICATION

a. The potential winner(s) will be notified by email. b. If a potential winner (i) does not respond to the notification attempt within one (1) week from the first notification attempt or (ii) notifies Kaggle within one week after the Final Submission Deadline that the potential winner does not want to be nominated as a winner or does not want to receive a Prize, then, in each case (i) and (ii) such potential winner will not receive any Prize, and an alternate potential winner will be selected from among all eligible entries received based on the Competition’s judging criteria. c. In case (i) and (ii) above Kaggle may disqualify the Participant. However, in case (ii) above, if requested by Kaggle, such potential winner may provide code and documentation to verify the Participant’s compliance with these Rules. If the potential winner provides code and documentation to the satisfaction of Kaggle, the Participant will not be disqualified pursuant to this paragraph. d. Competition Sponsor reserves the right to disqualify any Participant from the Competition if the Competition Sponsor reasonably believes that the Participant has attempted to undermine the legitimate operation of the Competition by cheating, deception, or other unfair playing practices or abuses, threatens or harasses any other Participants, Competition Sponsor or Kaggle. e. A disqualified Participant may be removed from the Competition leaderboard, at Kaggle's sole discretion. If a Participant is removed from the Competition Leaderboard, additional winning features associated with the Kaggle competition platform, for example Kaggle points or medals, may also not be awarded. f. The final leaderboard list will be publicly displayed at Kaggle.com. Determinations of Competition Sponsor are final and binding.

#### 9. PRIZES

a. Prize(s) are as described on the Competition Website and are only available for winning during the time period described on the Competition Website. The odds of winning any Prize depends on the number of eligible Submissions received during the Competition Period and the skill of the Participants. b. All Prizes are subject to Competition Sponsor's review and verification of the Participant’s eligibility and compliance with these Rules, and the compliance of the winning Submissions with the Submissions Requirements. In the event that the Submission demonstrates non-compliance with these Competition Rules, Competition Sponsor may at its discretion take either of the following actions: (i) disqualify the Submission(s); or (ii) require the potential winner to remediate within one week after notice all issues identified in the Submission(s) (including, without limitation, the resolution of license conflicts, the fulfillment of all obligations required by software licenses, and the removal of any software that violates the software restrictions). c. A potential winner may decline to be nominated as a Competition winner in accordance with Section 3.8. d. Potential winners must return all required Prize acceptance documents within two (2) weeks following notification of such required documents, or such potential winner will be deemed to have forfeited the prize and another potential winner will be selected. Prize(s) will be awarded within approximately thirty (30) days after receipt by Competition Sponsor or Kaggle of the required Prize acceptance documents. Transfer or assignment of a Prize is not allowed. e. You are not eligible to receive any Prize if you do not meet the Eligibility requirements in Section 2.7 and Section 3.1 above. f. If a Team wins a monetary Prize, the Prize money will be allocated in even shares between the eligible Team members, unless the Team unanimously opts for a different Prize split and notifies Kaggle before Prizes are issued.

#### 10. TAXES

a. ALL TAXES IMPOSED ON PRIZES ARE THE SOLE RESPONSIBILITY OF THE WINNERS. Payments to potential winners are subject to the express requirement that they submit all documentation requested by Competition Sponsor or Kaggle for compliance with applicable state, federal, local and foreign (including provincial) tax reporting and withholding requirements. Prizes will be net of any taxes that Competition Sponsor is required by law to withhold. If a potential winner fails to provide any required documentation or comply with applicable laws, the Prize may be forfeited and Competition Sponsor may select an alternative potential winner. Any winners who are U.S. residents will receive an IRS Form-1099 in the amount of their Prize.

#### 11. GENERAL CONDITIONS

a. All federal, state, provincial and local laws and regulations apply.

#### 12. PUBLICITY

a. You agree that Competition Sponsor, Kaggle and its affiliates may use your name and likeness for advertising and promotional purposes without additional compensation, unless prohibited by law.

#### 13. PRIVACY

a. You acknowledge and agree that Competition Sponsor and Kaggle may collect, store, share and otherwise use personally identifiable information provided by you during the Kaggle account registration process and the Competition, including but not limited to, name, mailing address, phone number, and email address (“Personal Information”). Kaggle acts as an independent controller with regard to its collection, storage, sharing, and other use of this Personal Information, and will use this Personal Information in accordance with its Privacy Policy <[www.kaggle.com/privacy](http://www.kaggle.com/privacy)>, including for administering the Competition. As a Kaggle.com account holder, you have the right to request access to, review, rectification, portability or deletion of any personal data held by Kaggle about you by logging into your account and/or contacting Kaggle Support at <[www.kaggle.com/contact](http://www.kaggle.com/contact)>. b. As part of Competition Sponsor performing this contract between you and the Competition Sponsor, Kaggle will transfer your Personal Information to Competition Sponsor, which acts as an independent controller with regard to this Personal Information. As a controller of such Personal Information, Competition Sponsor agrees to comply with all U.S. and foreign data protection obligations with regard to your Personal Information. Kaggle will transfer your Personal Information to Competition Sponsor in the country specified in the Competition Sponsor Address listed above, which may be a country outside the country of your residence. Such country may not have privacy laws and regulations similar to those of the country of your residence.

#### 14. WARRANTY, INDEMNITY AND RELEASE

a. You warrant that your Submission is your own original work and, as such, you are the sole and exclusive owner and rights holder of the Submission, and you have the right to make the Submission and grant all required licenses. You agree not to make any Submission that: (i) infringes any third party proprietary rights, intellectual property rights, industrial property rights, personal or moral rights or any other rights, including without limitation, copyright, trademark, patent, trade secret, privacy, publicity or confidentiality obligations, or defames any person; or (ii) otherwise violates any applicable U.S. or foreign state or federal law. b. To the maximum extent permitted by law, you indemnify and agree to keep indemnified Competition Entities at all times from and against any liability, claims, demands, losses, damages, costs and expenses resulting from any of your acts, defaults or omissions and/or a breach of any warranty set forth herein. To the maximum extent permitted by law, you agree to defend, indemnify and hold harmless the Competition Entities from and against any and all claims, actions, suits or proceedings, as well as any and all losses, liabilities, damages, costs and expenses (including reasonable attorneys fees) arising out of or accruing from: (a) your Submission or other material uploaded or otherwise provided by you that infringes any third party proprietary rights, intellectual property rights, industrial property rights, personal or moral rights or any other rights, including without limitation, copyright, trademark, patent, trade secret, privacy, publicity or confidentiality obligations, or defames any person; (b) any misrepresentation made by you in connection with the Competition; (c) any non-compliance by you with these Rules or any applicable U.S. or foreign state or federal law; (d) claims brought by persons or entities other than the parties to these Rules arising from or related to your involvement with the Competition; and (e) your acceptance, possession, misuse or use of any Prize, or your participation in the Competition and any Competition-related activity. c. You hereby release Competition Entities from any liability associated with: (a) any malfunction or other problem with the Competition Website; (b) any error in the collection, processing, or retention of any Submission; or (c) any typographical or other error in the printing, offering or announcement of any Prize or winners.

#### 15. INTERNET

a. Competition Entities are not responsible for any malfunction of the Competition Website or any late, lost, damaged, misdirected, incomplete, illegible, undeliverable, or destroyed Submissions or entry materials due to system errors, failed, incomplete or garbled computer or other telecommunication transmission malfunctions, hardware or software failures of any kind, lost or unavailable network connections, typographical or system/human errors and failures, technical malfunction(s) of any telephone network or lines, cable connections, satellite transmissions, servers or providers, or computer equipment, traffic congestion on the Internet or at the Competition Website, or any combination thereof, which may limit a Participant’s ability to participate.

#### 16. RIGHT TO CANCEL, MODIFY OR DISQUALIFY

a. If for any reason the Competition is not capable of running as planned, including infection by computer virus, bugs, tampering, unauthorized intervention, fraud, technical failures, or any other causes which corrupt or affect the administration, security, fairness, integrity, or proper conduct of the Competition, Competition Sponsor reserves the right to cancel, terminate, modify or suspend the Competition. Competition Sponsor further reserves the right to disqualify any Participant who tampers with the submission process or any other part of the Competition or Competition Website. Any attempt by a Participant to deliberately damage any website, including the Competition Website, or undermine the legitimate operation of the Competition is a violation of criminal and civil laws. Should such an attempt be made, Competition Sponsor and Kaggle each reserves the right to seek damages from any such Participant to the fullest extent of the applicable law.

#### 17. NOT AN OFFER OR CONTRACT OF EMPLOYMENT

a. Under no circumstances will the entry of a Submission, the awarding of a Prize, or anything in these Rules be construed as an offer or contract of employment with Competition Sponsor or any of the Competition Entities. You acknowledge that you have submitted your Submission voluntarily and not in confidence or in trust. You acknowledge that no confidential, fiduciary, agency, employment or other similar relationship is created between you and Competition Sponsor or any of the Competition Entities by your acceptance of these Rules or your entry of your Submission.

#### 18. DEFINITIONS

a. "Competition Data" are the data or datasets available from the Competition Website for the purpose of use in the Competition, including any prototype or executable code provided on the Competition Website. The Competition Data will contain private and public test sets. Which data belongs to which set will not be made available to Participants. b. An “Entry” is when a Participant has joined, signed up, or accepted the rules of a competition. Entry is required to make a Submission to a competition. c. A “Final Submission” is the Submission selected by the user, or automatically selected by Kaggle in the event not selected by the user, that is/are used for final placement on the competition leaderboard. d. A “Participant” or “Participant User” is an individual who participates in a competition by entering the competition and making a Submission. e. The “Private Leaderboard” is a ranked display of Participants’ Submission scores against the private test set. The Private Leaderboard determines the final standing in the competition. f. The “Public Leaderboard” is a ranked display of Participants’ Submission scores against a representative sample of the test data. This leaderboard is visible throughout the competition. g. A “Sponsor” is responsible for hosting the competition, which includes but is not limited to providing the data for the competition, determining winners, and enforcing competition rules. h. A “Submission” is anything provided by the Participant to the Sponsor to be evaluated for competition purposes and determine leaderboard position. A Submission may be made as a model, notebook, prediction file, or other format as determined by the Sponsor. i. A “Team” is one or more Participants participating together in a Kaggle competition, by officially merging together as a Team within the competition platform.
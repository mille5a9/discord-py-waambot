from asyncio import sleep
import nextcord as discord
import json
import datetime
import pytz
from typing import Optional
from pymongo import ASCENDING
from nextcord.ext import tasks, commands
from internal import constants
from inspect import currentframe, getframeinfo
from espn_api.football import League as EspnLeague, Player as EspnPlayer
from yfpy.data import Data
from yfpy.query import YahooFantasySportsQuery as YahooQuery
from yfpy.models import League, Team, Standings, Scoreboard, Matchup, Player, PlayerStats
from bs4 import BeautifulSoup
import requests

from database.FantasyManagers import FantasyManagers

LEAGUE_ID = 'league_id'

settings = None
with open('data/config.json') as f:
    settings = json.load(f)

class Yahoo(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # Data.retrieve(filename, yf_query, params=None, data_type_class=None, new_data_dir=None)
    controller = Data('../yahoo', True)

    # api id, secret, league_id
    config = None
    with open('data/private.json') as f:
        config = json.load(f)
    
    espnLeague = EspnLeague(
        int(config['espn_id']),
        int(config['year']),
        config['espn_s2'],
        config['espn_swid']
    )
        
    async def find_user(self, userId):
        return await FantasyManagers.find_one({'_id': userId, 'league': self.config[LEAGUE_ID]})
    
    async def find_all_users(self):
        return await FantasyManagers.find({'league': self.config[LEAGUE_ID]}).sort('team', ASCENDING).to_list(12)

    async def find_discord_user(self, userId):
        user = self.bot.get_user(userId)
        if (user is None):  user = await self.bot.fetch_user(userId)
        return user.display_name

    async def assign_user_to_team(self, userId: str, teamId: int):
        # ensure teamId is not bound already
        existing_binding = await FantasyManagers.find_one({'team': teamId})
        if (existing_binding is not None):
            return False
        
        # bind userId to team
        new_entry = FantasyManagers(user=userId)
        new_entry['team'] = teamId
        new_entry['league'] = self.config[LEAGUE_ID]
        await new_entry.commit()
        return True

    def parseUTCDateToTime(self, olddate: str): # date comes in as yyyy-MM-ddThh:mmZ
        tz = pytz.timezone(self.config['timezone'])
        time_string = olddate[11:16]
        utc_dt = pytz.utc.localize(datetime.datetime.strptime(time_string, '%H:%M')) - datetime.timedelta(minutes=4)
        return str(utc_dt.astimezone(tz).strftime("%I:%M%p"))

    def parseUTCDateToWeekdayTime(self, olddate: str):
        tz = pytz.timezone(self.config['timezone'])
        utc_dt = pytz.utc.localize(datetime.datetime.strptime(olddate, f'%Y-%m-%dT%H:%MZ'))
        return str(utc_dt.astimezone(tz).strftime(f'%a %I:%M%p'))

    def parseUTCDateToDate(self, olddate: str):
        tz = pytz.timezone(self.config['timezone'])
        utc_dt = pytz.utc.localize(datetime.datetime.strptime(olddate, f'%Y-%m-%dT%H:%MZ'))
        return str(utc_dt.astimezone(tz).strftime(f'%m-%d'))

    def getYahooQueryObject(self):
        return YahooQuery('data/', self.config[LEAGUE_ID])

    def getIntCurrentWeek(self):
        query = self.getYahooQueryObject()
        league: League = self.controller.retrieve(
            'league_metadata', 
            query.get_league_metadata
        )
        return int(league.current_week)

    def getLeagueTeamCount(self):
        query = self.getYahooQueryObject()
        league: League = self.controller.retrieve(
            'league_metadata', 
            query.get_league_metadata
        )
        return int(league.num_teams)

    def getLeagueInfo(self):
        query = self.getYahooQueryObject()
        return self.controller.retrieve(
            'league_info', 
            query.get_league_info
        )

    def getScoreboard(self, week: int):
        query = self.getYahooQueryObject()
        return self.controller.retrieve(
            'league_scoreboard_week_' + str(week), 
            query.get_league_scoreboard_by_week, 
            {'chosen_week': week}
        )

    def getStandings(self):
        query = self.getYahooQueryObject()
        return self.controller.retrieve(
            'league_standings', 
            query.get_league_standings
        )

    def getTeams(self):
        query = self.getYahooQueryObject()
        return self.controller.retrieve(
            'league_teams', 
            query.get_league_teams
        )

    def getTeam(self, teamid: int):
        query = self.getYahooQueryObject()
        teams = self.controller.retrieve(
            'league_teams', 
            query.get_league_teams
        )
        for team in teams:
            if team['team'].team_id == teamid: return team
        return None

    def getTeamPlayerStats(self, teamId: int, week: int):
        query = self.getYahooQueryObject()
        return self.controller.retrieve(
            ('team_' + str(teamId) + '_roster_player_stats_by_week_' + str(week)),
            query.get_team_roster_player_stats_by_week,
            {
                'team_id': str(teamId),
                'chosen_week': week
            }
        )

    # returns list of dictionaries of current week's NFL game info
    # assume week arg validated
    def getLiveGameStates(self, week: int):
        year = self.config['year']
        urlstr = f"https://www.espn.com/nfl/schedule/_/week/{str(week)}/year/{str(year)}/seasontype/2"
        response = requests.get(urlstr)
        page = BeautifulSoup(response.content, 'html.parser')
        schedule_tables = page.find_all(class_='ScheduleTables')
        out = []
        print(getframeinfo(currentframe()).lineno)
        for section in schedule_tables:
            # top loop is for the date, schedule_dates[i].text
            print(getframeinfo(currentframe()).lineno)

            # no games scheduled for this date if there is no table head
            if section.find('thead') is None:
                print(getframeinfo(currentframe()).lineno)
                continue

            # only take 3 headings if the 4th one is not "nat tv", as finished games would instead have a leading scorer listed
            headings_max = 4 if section.find_all('th')[2].text == 'TV' else 3

            # populate matches
            tbody = section.find('tbody')
            for row in tbody.find_all('tr'):
                print(getframeinfo(currentframe()).lineno)
                # Construct Dict object for out: list with each row
                cells = row.find_all('td')
                print(getframeinfo(currentframe()).lineno)

                # Get date, teams, and score for finished game
                if headings_max == 3: 
                    out.append({
                        'date': section.find(class_='Table__Title').text,
                        'team1': cells[0].find('a')['href'].split('/')[-2].upper(),
                        'team2': cells[1].find('a')['href'].split('/')[-2].upper(),
                        'score': cells[2].find('a').text
                    })
                    print(getframeinfo(currentframe()).lineno, out[-1]['date'],out[-1]['team1'],out[-1]['team2'],out[-1]['score'])
                # Get date, time, teams, and TV network for upcoming game
                elif headings_max == 4: 
                    out.append({
                        'date': section.find(class_='Table__Title').text,
                        'team1': cells[0].find('a')['href'].split('/')[-2].upper(),
                        'team2': cells[1].find('a')['href'].split('/')[-2].upper(),
                        'time': cells[2].text.replace(' ', ''),
                        'tv': cells[3].text
                    })
                    print(getframeinfo(currentframe()).lineno, out[-1]['date'],out[-1]['team1'],out[-1]['team2'],out[-1]['time'],out[-1]['tv'], (out[-1]['tv'] is None))
        return out

    # returns list of NFL game status strings formatted for gameday board
    def getLiveGameSlate(self):
        embed = discord.Embed(color=0x99AAB5)
        gameStates = self.getLiveGameStates(self.getIntCurrentWeek())
        for game in gameStates:
            if ('score' in game):
                scores = game['score'].split(', ')
                team1Score = scores[0].split()[1] if scores[0].split()[0] == game['team1'] else scores[1].split()[1]
                team2Score = scores[0].split()[1] if scores[0].split()[0] == game['team2'] else scores[1].split()[1]
                month = game['date'].split(' ')[1][:3]
                day = game['date'].split(' ')[2]
                date = '' + month + '/' + day
                n = '**' + game['team1'] + ' @ ' + game['team2'] + ' | ' + date + ' ' + game['time'] + '**'
                v = '' + game['team1full'] + ': ' + team1Score + '\n' + game['team2full'] + ': ' + team2Score
            else:
                month = constants.MONTH_ABBR_MAP[game['date'].split(' ')[1][:3]]
                day = game['date'].split(' ')[2]
                date = '' + month + '/' + day
                n = '**' + game['team1'] + ' @ ' + game['team2'] + ' | ' + date + ' ' + game['time'] + '**'
                v = '[Preview](https://www.youtube.com/watch?v=dQw4w9WgXcQ)'

            embed.add_field(name=n, value=v)
        return embed

    # this endpoint is only capable of getting the current week
    def getNFLScoreboardEndpoint(self, todayString = None):
        response = requests.get("http://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard")
        data = response.json()
        games: list = data['events']
        embed = discord.Embed(title='Week ' + str(data['week']['number']) + ' NFL Scoreboard', color=0x99AAB5)
        live = False
        for game in games:
            n = ''
            v = ''

            competitors = game['competitions'][0]['competitors']

            team1 = competitors[1] #away
            team2 = competitors[0] #home
            team1Name = team1['team']['shortDisplayName']
            team2Name = team2['team']['shortDisplayName']
            team1Record = ('(' + team1['records'][0]['summary'] + ')') if 'records' in team1 else ''
            team2Record = ('(' + team2['records'][0]['summary'] + ')') if 'records' in team2 else ''
            team1Score = team1['score']
            team2Score = team2['score']
            
            # if present game, else if future game, else if past game
            if ('situation' in game['competitions'][0]): #present
                live = True

                situation = game['competitions'][0]['situation']
                if ('possession' in situation and situation['possession'] == team1['id']): team1Name = '\>' + team1Name
                elif ('possession' in situation and situation['possession'] == team2['id']): team2Name = '\>' + team2Name
                dnd = situation['downDistanceText'] if ('downDistanceText' in situation) else ''
                lastPlay = situation['lastPlay']['text'] if 'lastPlay' in situation else 'Waiting for first play...'
                clock = game['status']['type']['shortDetail']

                gamecast = '[Gamecast](' + game['links'][0]['href'] + ') '
                boxScore = '[Box Score](' + game['links'][1]['href'] + ') '
                playByPlay = '[Play-by-Play](' + game['links'][2]['href'] + ')'

                n = clock + '|' + dnd
                v = (team1Name + ' ' + team1Record) + ':\t' + team1Score + '\n'
                v += (team2Name + ' ' + team2Record) + ':\t' + team2Score + '\n'
                v += lastPlay + '\n' + gamecast + boxScore + playByPlay

            elif ('odds' in game['competitions'][0]): #future
                if (self.parseUTCDateToDate(game['date']) == todayString): live = True
                odds = game['competitions'][0]['odds']
                line = odds[0]['details']
                overUnder = odds[0]['overUnder']
                gamecast = '[Gamecast](' + game['links'][0]['href'] + ')'
                scheduleTime = self.parseUTCDateToWeekdayTime(game['date'])
                abbrMatchup = game['shortName']

                n = scheduleTime + ' | ' + abbrMatchup
                v = team1Name + ' ' + team1Record + '\n' + team2Name + ' ' + team2Record + '\n'
                v += line + ' | O/U: ' + str(overUnder) + ' ' + gamecast
            else: #past
                final = 'Final'
                abbrMatchup = game['shortName']

                boxScore = '[Box Score](' + game['links'][1]['href'] + ') '

                n = final + ' | ' + abbrMatchup
                v = (team1Name + ' ' + team1Record) + ':\t' + team1Score + '\n'
                v += (team2Name + ' ' + team2Record) + ':\t' + team2Score + '\n'
                v += boxScore

            embed.add_field(name=n, value=v)
        return (live, embed)

    async def validateWeekArg(self, ctx, week: int):
        if (week > 16):
            await ctx.send('`Week` parameter is out of bounds. Try something less than 17.')
            return (False, week)
        week = self.getIntCurrentWeek() if week == 0 else week
        return (True, week)
    
    async def validateMatchupArg(self, ctx, scoreboard: Scoreboard, matchup: int):
        userTeam = 0
        if matchup == 0:
            existing_entry = await self.find_user(str(ctx.author.id))
            userTeam = existing_entry['team']
        elif matchup > len(scoreboard.matchups):
            await ctx.send('`matchup` parameter is out of bounds. This league/week only has ' + str(len(scoreboard.matchups)) + ' matchups.')
            return (False, matchup)
        else: 
            return (True, matchup)
            
        # Find matchup number if the user did not provide a number, assuming they are checked to be registered by decorator
        for index, matchupObj in enumerate(scoreboard.matchups):
            if (matchupObj['matchup'].teams[0]['team'].team_id == userTeam or matchupObj['matchup'].teams[1]['team'].team_id == userTeam):
                matchup = (index + 1) 
                break
        return (True, matchup)

    async def validateTeamArg(self, ctx, teamId: int):
        teams = self.getTeams()

        # Find team number if the user did not provide a number, assuming they are checked to be registered by decorator
        existing_entry = await self.find_user(str(ctx.author.id))
        if (teamId < 0 or teamId > len(teams) or (existing_entry is None and teamId == 0)):
            await ctx.send('`teamid` parameter is out of bounds. This league only has ' + str(len(teams)) + ' teams, and `' + str(teamId) + '` is not one of them.')
            return (False, None)

        if teamId == 0: teamId = existing_entry['team']
        for team in teams:
            if int(team['team'].team_id) == teamId:
                return (True, team['team'])

    def refresh_espn_player_list(self):
        self.espnLeague.player_map = {}
        data = self.espnLeague.espn_request.get_pro_players()
        # Map all player id's to player name
        for player in data:
            # two way map to find playerId's by name
            self.espnLeague.player_map[player['id']] = player['fullName'] + '_' + str(player['defaultPositionId'])
            # if two players have the same fullname use first one for now TODO update for multiple player names
            # if (player['fullName'] + '_' + str(player['defaultPositionId'])) not in self.espnLeague.player_map:
            self.espnLeague.player_map[player['fullName'] + '_' + str(player['defaultPositionId'])] = player['id']

    def espn_player_map_get_wrapper(self, key: str):
        print('getting from player map: ' + key)
        output = self.espnLeague.player_map.get(key)
        print(output)
        return output if output is not None else 0

    # get player info from list of IDs, and pad the end with None for any missing info on part of the API
    # (Thanks, Robbie Anderson...)
    def espn_player_info_wrapper(self, playerId: list):
        output = self.espnLeague.player_info(playerId=playerId)
        while (len(output) < len(playerId)): output.append(None)
        return output

    # Sorts through playerNames list an assigns them in an alternating fashion to team1 and team2 projections
    def get_all_player_projections(self, playerNames, week: int):
        self.refresh_espn_player_list()
        
        # split monolithic list into odds and evens
        # team1playerNames = playerNames[::2]
        # team2playerNames = playerNames[1::2]

        # get ids lists from names lists and the player map that got refreshed above
        playerIds = list(self.espn_player_map_get_wrapper(name) for name in playerNames)
        # team2PlayerIds = list(self.espn_player_map_get_wrapper(name) for name in team2playerNames)

        # Get player info and sort back to the order the IDs came in
        players: list[EspnPlayer] = self.espn_player_info_wrapper(playerId=playerIds)
        players.sort(key=lambda x: playerIds.index(0 if x is None else x.playerId))

        # players2: list[EspnPlayer] = self.espn_player_info_wrapper(playerId=team2PlayerIds)
        # players2.sort(key=lambda x: team2PlayerIds.index(0 if x is None else x.playerId))

        def getProjections(players: list, week: int):
            teamProjections = []
            for playerObj in players:
                player: EspnPlayer = playerObj
                tempFloat: float = 0.0

                # Check if weekly projection is not out (offseason)
                if (player is None or week not in player.stats):
                    pass

                # Check if projection section exists (game has not yet been played, happy path)
                elif ('projected_breakdown' in player.stats[week]):
                    projRec: float = 0.0 if 'receivingReceptions' not in player.stats[week]['projected_breakdown'] else player.stats[week]['projected_breakdown']['receivingReceptions']
                    projPassInt: float = 0.0 if 'passingInterceptions' not in player.stats[week]['projected_breakdown'] else player.stats[week]['projected_breakdown']['passingInterceptions']
                    tempFloat = round((player.stats[week]['projected_points'] - (projRec / 2) + projPassInt), 2)

                else:
                    rec: float = 0.0 if 'receivingReceptions' not in player.stats[week]['breakdown'] else player.stats[week]['breakdown']['receivingReceptions']
                    passInt: float = 0.0 if 'passingInterceptions' not in player.stats[week]['breakdown'] else player.stats[week]['breakdown']['passingInterceptions']
                    tempFloat = round((float(player.stats[week]['points']) - (rec / 2) + passInt), 2)

                teamProjections.append(tempFloat)
            return teamProjections

        return (getProjections(players, int(week)))

    def do_matchup(self, matchupObj, matchupCount: int):
        embedName = ''
        embedValue = '```'

        matchup: Matchup = matchupObj['matchup']
        week = matchup.week
        embedName = 'Week ' + str(week) + ' Matchup ' + str(matchupCount) + ':'

        team1: Team = matchup.teams[0]['team']
        team2: Team = matchup.teams[1]['team']
        manager1: str = ' (' + team1.managers['manager'].nickname + ')'
        manager2: str = ' (' + team2.managers['manager'].nickname + ')'
        # Total line length: 61 (Discord embed capable of 62 with 16px font and 125% zoom which is what I use)
        embedValue += '' + (str(team1.name, 'UTF-8') + manager1)[:28].rjust(28, ' ') + ' vs. ' + (str(team2.name, 'UTF-8') + manager2)[:28].ljust(28, ' ') + '\n'

        players1 = self.getTeamPlayerStats(team1.team_id, week)
        players2 = self.getTeamPlayerStats(team2.team_id, week)

        # Take out bench players to streamline the char count
        sortedPlayers1 = list(
            player for player in players1 if (
                player['player'].selected_position.position != 'BN' and 
                player['player'].selected_position.position != 'IR'
                )
            )
        sortedPlayers2 = list(
            player for player in players2 if (
                player['player'].selected_position.position != 'BN' and 
                player['player'].selected_position.position != 'IR'
                )
            )
        
        # Write out player scoring by position (bench omitted for brevity)
        smallerPlayerCount = len(sortedPlayers1) if len(sortedPlayers1) < len(sortedPlayers2) else len(sortedPlayers2)

        # Compile list of player strings to fetch projections
        allPlayerNames = []
        for i in range(smallerPlayerCount):
            if (sortedPlayers1[i]['player'].selected_position.position == 'DEF'): allPlayerNames.append(
                (sortedPlayers1[i]['player'].editorial_team_full_name.split(' ')[-1] + ' D/ST_16')
            )
            else: allPlayerNames.append(sortedPlayers1[i]['player'].full_name + '_' + str(constants.POSITION_MAP[sortedPlayers1[i]['player'].primary_position]))
            if (sortedPlayers2[i]['player'].selected_position.position == 'DEF'): allPlayerNames.append(
                (sortedPlayers2[i]['player'].editorial_team_full_name.split(' ')[-1] + ' D/ST_16')
            )
            else: allPlayerNames.append(sortedPlayers2[i]['player'].full_name + '_' + str(constants.POSITION_MAP[sortedPlayers2[i]['player'].primary_position]))
        team1Projections = self.get_all_player_projections(allPlayerNames[::2], week)
        team2Projections = self.get_all_player_projections(allPlayerNames[1::2], week)

        for i in range(smallerPlayerCount):
            player1: Player = sortedPlayers1[i]['player']
            player2: Player = sortedPlayers2[i]['player']
            name1 = ('' + player1.first_name[:1] + '.' + player1.last_name) if player1.last_name is not None else player1.full_name
            name2 = ('' + player2.first_name[:1] + '.' + player2.last_name) if player2.last_name is not None else player2.full_name
            proj1 = ('(' + (str(team1Projections[i]) + (' ' if str(team1Projections[i])[-2] == '.' else '')).rjust(5, ' ') + ')')
            proj2 = ('(' + ((' ' if team2Projections[i] < 10.0 else '') + str(team2Projections[i])).ljust(5, ' ') + ')')
            points1 = '0.0 ' if player1.player_points.total is None else (str(player1.player_points.total) + (' ' if str(player1.player_points.total)[-2] == '.' else ''))
            points2 = ' 0.0' if player2.player_points.total is None else ((' ' if player2.player_points.total < 10.0 else '') + str(player2.player_points.total))
            position = 'FLX' if player1.selected_position.position == 'W/R/T' else player1.selected_position.position
            number1 = ('#' + str(player1.uniform_number)) if (player1.uniform_number is not False and player1.uniform_number is not None) else '    '
            number2 = (' #' + str(player2.uniform_number)) if (player2.uniform_number is not False and player2.uniform_number is not None) else '     '
            teamcode1 = player1.editorial_team_abbr
            teamcode2 = player2.editorial_team_abbr
            # 29 + 3 + 29 = 61 chars wide
            embedValue += '' + teamcode1.ljust(4, ' ') + number1.ljust(4, ' ') + name1[:8].ljust(8, ' ') + proj1.rjust(7, ' ') + str(points1).rjust(5, ' ') + ' '
            embedValue += position.ljust(3, ' ')
            embedValue += ' ' + str(points2).ljust(5, ' ') + proj2.ljust(7, ' ') + name2[:8].rjust(8, ' ') + number2.ljust(5, ' ') + teamcode2.rjust(3, ' ') + '\n'        

        # Totals line /w total prediction
        embedValue += '(Proj) Total ' + ('(' + str(team1.team_projected_points.total) + ') ' + str(team1.team_points.total)).rjust(15, ' ') + ' TOT '
        embedValue += ('' + str(team2.team_points.total) + ' (' + str(team2.team_projected_points.total) + ')').ljust(15, ' ') + ' Total (Proj)```'

        return embedName, embedValue

    def enforce_sports_channel():
        async def predicate(ctx):
            type = str(ctx.channel.type)

            if ctx.guild is not None and (
                (str(ctx.guild.name) != 'Dedotated waam' and str(ctx.guild.name) != 'An-D\'s waambot dev') or 
                (type == 'text' and str(ctx.channel.name) != settings['sports_channel']) or
                (type == 'public_thread' and ctx.channel.parent.name != settings['sports_channel'])):
                
                print('ff command used outside of sports channel but not in a DM, skipping..\n')
                await ctx.send(':rotating_light: Cannot use a waambot ff command in this channel')
                return False
            return True
        return commands.check(predicate)

    def enforce_user_registered():
        async def predicate(ctx):
            with open('data/private.json') as f:
                config = json.load(f)
                existing_user = await FantasyManagers.find_one({'_id': str(ctx.author.id), 'league': config[LEAGUE_ID]})
                if (existing_user is None): 
                    await ctx.send(':rotating_light: You must be registered to use this command. Use `wb ff league` to find your team and `wb ff register [ID]` to register.')
                    return False
                else: return True
        return commands.check(predicate)

    @commands.group(aliases=['yahoo', 'fantasy'])
    async def ff(self, ctx): 
        """
        Reads information on the locally configured Yahoo Fantasy Football League. Also provides a live updating gameday thread with NFL scoreboard and community-relevant FF matchups.
        """
        pass

    @ff.command()
    @enforce_user_registered()
    @enforce_sports_channel()
    async def test(self, ctx):
        """
        A test command, which can be used to test components.
        """
        print('Successful Yahoo FF test\n')
        msg = await ctx.send('Successful Yahoo FF test')
 
    @ff.command(name='register')
    @enforce_sports_channel()
    async def register(self, ctx, teamNo: int):
        """
        Register a team in the league to yourself. This facilitates other commands such as `wb ff team` to show you your own team by default.
        """
        async with ctx.channel.typing():
            # Pull team ID info
            leagueTeams = self.getTeams()

            # Stop if teamNo is bad
            if (teamNo < 0 or teamNo > len(leagueTeams)):
                await ctx.send(":rotating_light: Invalid Team ID number. Check IDs by using `wb ff league` and try again.")
                return

            # Check for commanding user in the FantasyManagers mongodb doc
            existing_entry = await self.find_user(str(ctx.author.id))

        # If this is a new user
        if (existing_entry is None):
            result = await self.assign_user_to_team(str(ctx.author.id), teamNo)
            if result is True:
                await ctx.send('Success! ' + ctx.author.name + ' has been bound with team number ' + str(teamNo) + '.')
            else:
                await ctx.send('Error! Team number ' + str(teamNo) + ' has already been claimed by another user in this channel.')
        else:
            await ctx.send('Error! You have already registered to a team in this channel. If you want to change your registration, use `wb ff unregister`')

    @ff.command(name='unregister')
    @enforce_sports_channel()
    async def unregister(self, ctx):
        """
        Remove the binding between your discord user ID and one of the team IDs in the league.
        """
        # Check for commanding user in the FantasyManagers mongodb doc
        existing_entry = await self.find_user(str(ctx.author.id))
        if (existing_entry is None):
            await ctx.send('You are not currently registered to a team in this channel. Use `wb ff league` to find your team\'s ID number and then `wb ff register [number]`')
        else:
            await existing_entry.delete()
            await ctx.send('Success! Binding for ' + ctx.author.name + ' has been removed.')

    @ff.command(name='league')
    @enforce_sports_channel()
    async def league(self, ctx):
        """
        Retrieve Yahoo Fantasy teams and IDs.
        """
        async with ctx.channel.typing():
            leagueTeams = self.getTeams()

            output = '  # | Team Name              | Manager(s)   \n'
            for i in leagueTeams:
                team: Team = i['team']
                id = ' ' + str(team.team_id).rjust(2, ' ') + ' |'
                name = ' ' + str(team.name, 'UTF-8').ljust(22, ' ') + ' |'
                managers = ' ' + team.managers['manager'].nickname

                output += (id + name + managers).ljust(44, ' ') + '\n'

            embed: discord.Embed = discord.Embed(color=0x99AAB5)
            embed.add_field(name='League: ' + constants.YAHOO_FANTASY_LEAGUE_NAME, value='```' + output + '```')

        msg = await ctx.send(embed=embed)

    @ff.command(name='standings')
    @enforce_sports_channel()
    async def standings(self, ctx):
        """
        Display the current standings page for the fantasy league.
        """
        async with ctx.channel.typing():
            standings: Standings = self.getStandings()

            top3 = 'Rank|' + 'Team Name'.ljust(19, ' ') + '| W-L-T |Pts For|Pts Agn|Strk|Wv|Mv\n'
            for teamObj in standings.teams:
                team: Team = teamObj['team']
                rank = '   0|' if team.team_standings.rank is None else (str(team.team_standings.rank) + '|').rjust(5, ' ')
                name = '' + str(team.name, 'UTF-8')[:19].ljust(19, ' ') + '|'
                wlt = '' + str(team.wins).rjust(2, ' ') + ('-' + str(team.losses) + '-' + str(team.ties)).ljust(5, ' ') + '|'
                ptsFor = '' + (str(round(team.points_for, 2)) + ('0' if str(round(team.points_for, 2))[-2] == '.' else '')).rjust(7, ' ') + '|'
                ptsAgnst = '' + (str(round(team.points_against, 2)) + ('0' if str(round(team.points_against, 2))[-2] == '.' else '')).rjust(7, ' ') + '|'
                streak = '' + (' ' if team.streak_type == '' else team.streak_type[:1].upper()) + '-' + str(team.streak_length).ljust(2, ' ') + '|'
                waiver = '' + ('0' if team.waiver_priority is None else str(team.waiver_priority)).rjust(2, ' ') + '|'
                moves = '' + ('0' if team.number_of_moves is None else str(team.number_of_moves)).rjust(2, ' ')
                top3 += rank + name + wlt + ptsFor + ptsAgnst + streak + waiver + moves + '\n'

            embed: discord.Embed = discord.Embed(color=0x99AAB5)
            embed.add_field(name=('' + self.config['league_name'] + ' Standings'), value='```' + top3 + '```', inline=True)

        msg = await ctx.send(embed=embed)

    # potentially include live IRL NFL scoreboard stuff with this, and extend that to the gameday routine.
    @ff.command(name='scoreboard')
    @enforce_sports_channel()
    @enforce_user_registered()
    async def scoreboard(self, ctx, week: int = 0):
        """
        Display the current scoreboard for the fantasy league. Optional week parameter for retrospective/lookahead.
        """
        start = datetime.datetime.now()
        valid, week = await self.validateWeekArg(ctx, week)
        if (not valid): return

        async with ctx.channel.typing():

            scoreboard: Scoreboard = self.getScoreboard(week)
            embedNames = [None] * len(scoreboard.matchups)
            embedValues = [None] * len(scoreboard.matchups)
        
            for i in range(len(scoreboard.matchups)):
                embedNames[i], embedValues[i] = self.do_matchup(scoreboard.matchups[i], i + 1)

            # Create discord thread for all these messages
            scoreThread = await ctx.message.create_thread(name='Week ' + str(week) + ' Scoreboard')

            # split do_matchup output into alternative lists 
            # to be combined for two-per-discord-message
            
            embeds = []
            for n, v in zip(embedNames, embedValues): 
                embed = discord.Embed(color=0x99AAB5)
                embed.add_field(name=n, value=v, inline=False)
                embeds.append(embed)
        msg = await scoreThread.send(embeds=embeds)

        end = datetime.datetime.now()
        print(start)
        print(end)

    @ff.command(name='matchups')
    @enforce_sports_channel()
    async def matchups(self, ctx, week: int = 0):
        """
        Displays the team names for each matchup. Use to find specific matchup IDs without waiting for the scoreboard. 
        """
        valid, week = await self.validateWeekArg(ctx, week)
        if (not valid): return
        async with ctx.channel.typing():

            scoreboard: Scoreboard = self.getScoreboard(week)
            title = 'Week ' + str(week) + ' Matchups:'
            output = ''
            for index, matchupObj in enumerate(scoreboard.matchups, start=1):
                matchup: Matchup = matchupObj['matchup']

                team1: Team = matchup.teams[0]['team']
                team2: Team = matchup.teams[1]['team']
                manager1: str = ' (' + team1.managers['manager'].nickname + ')'
                manager2: str = ' (' + team2.managers['manager'].nickname + ')'
                output += '' + str(index) + ': ' + (str(team1.name, 'UTF-8') + manager1)[:26].rjust(26, ' ') + ' vs. ' + (str(team2.name, 'UTF-8') + manager2)[:26].ljust(26, ' ') + '\n'

            embed: discord.Embed = discord.Embed(color=0x99AAB5)
            embed.add_field(name=title, value='```' + output + '```')
        msg = await ctx.send(embed=embed)

    @ff.command(name='matchup')
    @enforce_sports_channel()
    @enforce_user_registered()
    async def matchup(self, ctx, matchup: Optional[int] = 0, week: Optional[int] = 0):
        """
        Display the current matchup for your fantasy team. Optional matchup ID parameter for viewing other matchups - requires getting the ID from the scoreboard output.
        Further optional week parameter for specific matchups in specific weeks
        """
        valid, week = await self.validateWeekArg(ctx, week)
        if (not valid): return

        scoreboard = self.getScoreboard(week)
        valid, matchup = await self.validateMatchupArg(ctx, scoreboard, matchup)
        if (not valid): return

        async with ctx.channel.typing():
            # write matchup with the same code that writes the scoreboard, then send to discord non-threaded
            embedName, embedValue = self.do_matchup(scoreboard.matchups[matchup-1], matchup)
            embed = discord.Embed(color=0x99AAB5)
            embed.add_field(name=embedName, value=embedValue, inline=False)
        msg = await ctx.send(embed=embed)
        
    @ff.command(name='team')
    @enforce_sports_channel()
    @enforce_user_registered()  
    async def team(self, ctx, teamId: Optional[int] = 0, week: Optional[int] = 0):
        """
        Display the current matchup for your fantasy team. Optional team ID parameter for viewing other matchups - requires getting the ID from the `league` output.
        """
        valid, team = await self.validateTeamArg(ctx, teamId)
        if (not valid): return

        valid, week = await self.validateWeekArg(ctx, week)
        if (not valid): return

        async with ctx.channel.typing():

            players = self.getTeamPlayerStats(team.team_id, week)
            playerNames = []
            for player in players:
                if (player['player'].primary_position == 'DEF'): playerNames.append((player['player'].editorial_team_full_name.split(' ')[-1] + ' D/ST_16'))
                else: playerNames.append(player['player'].full_name + '_' + str(constants.POSITION_MAP[player['player'].primary_position]))
            teamProjections = self.get_all_player_projections(playerNames, week)

            gameStates = self.getLiveGameStates(week)

            def findGameForPlayer(games: list, player: Player):
                abbr = player.editorial_team_abbr.upper()
                opponent = ''
                for game in games:
                    if (game['team1'] == abbr): 
                        opponent = ' @ ' + game['team2']
                    elif (game['team2'] == abbr):
                        opponent = ' v ' + game['team1']
                    else: continue
                    if 'tv' in game: # not yet played game
                        weekday = game['date'].split(', ')[0][:3]
                        return (weekday + ' ' + game['time'] + opponent.ljust(6, ' ') + ' on ' + ('ABC' if game['tv'] is '' else game['tv']))
                    else: # game is over or in progress
                        scores = game['score'].split(', ')
                        winnerPts = scores[0].split()[1]
                        loserPts = scores[1].split()[1]
                        playerWon = True if scores[0].split()[0] == abbr else False
                        return ('Final ' + ('W' if playerWon else 'L') + ' ' + winnerPts + '-' + loserPts.ljust(2, ' ') + opponent)
                return 'Game Info Not Found'

            embedTitle = 'Team ' + str(team.team_id) + ' (Week ' + str(week) + '):'
            embedValues = ['   | ' + 'Info'.ljust(11, ' ') + '|' + 'Player'.ljust(10, ' ') + ' | ' + 'Pnts.'.ljust(6, ' ') + '| Game\n'] * 2

            # output these players in an all new formatted code-block table
            for i, playerObj in enumerate(players):
                player: Player = playerObj['player']
                embedIndex = 0
                if (player.selected_position.position == 'BN' or player.selected_position.position == 'IR'): embedIndex = 1
                selectedPosition = 'FLX' if player.selected_position.position == 'W/R/T' else player.selected_position.position
                abbr = player.editorial_team_abbr.ljust(3, ' ')
                number = ('#' + str(player.uniform_number)).ljust(4, ' ') if (player.uniform_number is not False and player.uniform_number is not None) else '    '
                primaryPosition = (player.primary_position).ljust(3, ' ')
                name = ('' + player.first_name[:1] + '.' + player.last_name) if player.last_name is not None else player.full_name
                points = ' 0.0 ' if player.player_points.total is None else ((' ' if player.player_points.total < 10.0 else '') + str(player.player_points.total))
                proj = (str(teamProjections[i]) + (' ' if str(teamProjections[i])[-2] == '.' else ''))
                if (points == ' 0.0 '): points = proj
                game = findGameForPlayer(gameStates, player)
                embedValues[embedIndex] += '' + selectedPosition.ljust(3, ' ') + '| ' + abbr + ' ' + number + primaryPosition + '|' + name[:10].ljust(10, ' ') + ' | ' + points.ljust(5, ' ') + ' | ' + game[:23] + '\n'
                
            embed = discord.Embed(color=0x99AAB5)
            embed.add_field(name=embedTitle, value=('```' + embedValues[0] + '```'), inline=False)
            embed.add_field(name='Bench', value=('```' + embedValues[1] + '```'), inline=False)
        msg = await ctx.send(embed=embed)

        
    @ff.command(name='gameday')
    @enforce_sports_channel()
    @enforce_user_registered()
    async def gameday(self, ctx):
        """
        Display and pin the league scoreboard with live updates (edits) every 60s until the day's games are over.
        """

        async with ctx.channel.typing():
            # get all registered users and their teams
            print(getframeinfo(currentframe()).lineno)
            userList = await self.find_all_users()
            scoreboard: Scoreboard = self.getScoreboard(self.getIntCurrentWeek())
            relevantMatchups = []
            accountedTeamIds = []
            for matchupObj in scoreboard.matchups:
                matchup: Matchup = matchupObj['matchup']
                for user in userList:
                    teamId = user.team
                    # skip accounted-for team
                    if (teamId in accountedTeamIds): continue
                    # account for both teams
                    if (teamId == matchup.teams[0]['team'].team_id or teamId == matchup.teams[1]['team'].team_id):
                        relevantMatchups.append(matchupObj)
                        accountedTeamIds.append(matchup.teams[0]['team'].team_id)
                        accountedTeamIds.append(matchup.teams[1]['team'].team_id)
                        break
            
            embedNames = [None] * len(relevantMatchups)
            embedValues = [None] * len(relevantMatchups)
        
            for i in range(len(relevantMatchups)):
                embedNames[i], embedValues[i] = self.do_matchup(relevantMatchups[i], i + 1)
                        # Create discord thread for all these messages
            
            embeds = []
            for n, v in zip(embedNames, embedValues): 
                embed = discord.Embed(color=0x99AAB5)
                embed.add_field(name=n, value=v, inline=False)
                embeds.append(embed)

            nowDateString = self.parseUTCDateToDate(datetime.datetime.now().strftime(f'%Y-%m-%dT%H:%MZ'))

            # All game info
            live, NFLembed = self.getNFLScoreboardEndpoint(nowDateString)
            embeds.append(NFLembed)

        gamedayThread = await ctx.message.create_thread(name='Gameday ' + nowDateString)
        msg = await gamedayThread.send(embeds=embeds)
        
        if (live):
            print("Starting gameday loop")
            self.gamedayLoop.start(msg=msg)
        else:
            print("Not live: no looping")

    # edits the gameday matchups/scoreboard every 60 seconds with up-to-the-minute information
    @tasks.loop(seconds=60)
    async def gamedayLoop(self, msg):
        print("Beginning a loop")
        
        async with msg.channel.typing():
            # get all registered users and their teams
            print(getframeinfo(currentframe()).lineno)
            userList = await self.find_all_users()
            scoreboard: Scoreboard = self.getScoreboard(self.getIntCurrentWeek())
            relevantMatchups = []
            accountedTeamIds = []
            for matchupObj in scoreboard.matchups:
                matchup: Matchup = matchupObj['matchup']
                for user in userList:
                    teamId = user.team
                    # skip accounted-for team
                    if (teamId in accountedTeamIds): continue
                    # account for both teams
                    if (teamId == matchup.teams[0]['team'].team_id or teamId == matchup.teams[1]['team'].team_id):
                        relevantMatchups.append(matchupObj)
                        accountedTeamIds.append(matchup.teams[0]['team'].team_id)
                        accountedTeamIds.append(matchup.teams[1]['team'].team_id)
                        break
            
            embedNames = [None] * len(relevantMatchups)
            embedValues = [None] * len(relevantMatchups)
        
            for i in range(len(relevantMatchups)):
                embedNames[i], embedValues[i] = self.do_matchup(relevantMatchups[i], i + 1)
            
            embeds = []
            for n, v in zip(embedNames, embedValues): 
                embed = discord.Embed(color=0x99AAB5)
                embed.add_field(name=n, value=v, inline=False)
                embeds.append(embed)

            nowDateString = self.parseUTCDateToDate(datetime.datetime.now().strftime(f'%Y-%m-%dT%H:%MZ'))

            # All game info
            live, NFLembed = self.getNFLScoreboardEndpoint(nowDateString)
            embeds.append(NFLembed)
        msg = await msg.edit(embeds=embeds)
        print("Ending a loop at " + str(datetime.datetime.now()))

        if not live: 
            print("Stopping gameday loop")
            await sleep(300)
            await msg.channel.send('Today\'s games have ended.')
            self.gamedayLoop.stop()

def setup(bot):
    bot.add_cog(Yahoo(bot))

import discord
from discord import app_commands
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import os
from dotenv import load_dotenv
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import io
import traceback
import random

load_dotenv()

# Google Sheets Setup
scope = ['https://spreadsheets.google.com/feeds',
         'https://www.googleapis.com/auth/drive']
creds = ServiceAccountCredentials.from_json_keyfile_name('credentials.json', scope)
client = gspread.authorize(creds)

# Emoji Configuration
EMOJIS = {
    "red": "🔴",
    "blue": "🔵",
    "green": "🟢",
    "yellow": "🟡",
    "1st": "🥇",
    "2nd": "🥈",
    "3rd": "🥉",
}

class BattleStatsBot(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
        self.sheet = None
        self.config_sheet = None
        self.message_id = None
        self.channel_id = None

    async def setup_hook(self):
        try:
            spreadsheet = client.open("Gauntlet 3 Player Stats")
            self.sheet = spreadsheet.worksheet("Round 1")
            self.config_sheet = spreadsheet.worksheet("Config")

            # Get all values from the Config sheet (vertical format)
            config_values = self.config_sheet.get_all_values()

            # Convert to dictionary {message_id: x, channel_id: y}
            config_dict = {}
            for row in config_values:
                if len(row) >= 2:  # Ensure there's a key and value
                    key = row[0].strip().lower()
                    value = row[1].strip()
                    config_dict[key] = value

            # Parse IDs (now works with vertical or horizontal formats)
            self.message_id = int(config_dict.get('message_id')) if config_dict.get('message_id', '').isdigit() else None
            self.channel_id = int(config_dict.get('channel_id')) if config_dict.get('channel_id', '').isdigit() else None

        except Exception as e:
            print(f"Error in setup_hook: {e}")
            traceback.print_exc()
            self.message_id = None
            self.channel_id = None

    async def generate_scoreboard_image(self, data):
        try:
            # Image dimensions
            width, height = 800, 2490
            background_color = (30, 30, 40)  # Dark background

            # Create base image
            img = Image.new('RGBA', (width, height), background_color)
            draw = ImageDraw.Draw(img)

            # Font setup (try modern fonts first)
            try:
                title_font = ImageFont.truetype("Inter-Bold.ttf", 42)
                player_font = ImageFont.truetype("Inter-SemiBold.ttf", 32)
                stat_font = ImageFont.truetype("Inter-Regular.ttf", 28)
            except:
                # Fallback to Arial if Inter is not available
                try:
                    title_font = ImageFont.truetype("arialbd.ttf", 42)
                    player_font = ImageFont.truetype("arialbd.ttf", 32)
                    stat_font = ImageFont.truetype("arial.ttf", 28)
                except:
                    # Final fallback to default font
                    title_font = ImageFont.load_default(42)
                    player_font = ImageFont.load_default(32)
                    stat_font = ImageFont.load_default(28)

            # Title
            title = "Gauntlet of Chaos"
            subtitle = "Leaderboard"

            # Draw title (using textbbox for modern Pillow versions)
            title_bbox = draw.textbbox((0, 0), title, font=title_font)
            title_w, title_h = title_bbox[2] - title_bbox[0], title_bbox[3] - title_bbox[1]
            draw.text(((width - title_w) / 2, 40), title, fill=(220, 180, 40), font=title_font)

            # Draw subtitle
            subtitle_bbox = draw.textbbox((0, 0), subtitle, font=title_font)
            subtitle_w, subtitle_h = subtitle_bbox[2] - subtitle_bbox[0], subtitle_bbox[3] - subtitle_bbox[1]
            draw.text(((width - subtitle_w) / 2, 90), subtitle, fill=(220, 220, 220), font=title_font)

            y_position = 160

            # Team colors
            team_colors = {
                'red': (255, 80, 80),
                'blue': (80, 80, 255),
                'green': (80, 220, 80),
                'yellow': (255, 220, 80)
            }

            # Card styling
            card_width = 700
            card_padding = 20
            card_margin = 20
            radius = 15

            # Process leaderboard data to get player rankings
            leaderboard = {}
            for p in data.get('leaderboard', []):
                if 'Combatant' in p:
                    leaderboard[p['Combatant'].lower()] = {
                        'position': p.get('Position', ''),
                        'team': p.get('Team', '').lower(),
                        'points': int(p.get('Points', 0)) if str(p.get('Points', 0)).isdigit() else 0
                    }

            # Combine all players from all teams
            all_players = []
            for team in ['red_team', 'blue_team', 'green_team', 'yellow_team']:
                for player in data.get(team, []):
                    player_data = {
                        'name': player.get('Name', 'Unknown'),
                        'team': player.get('Team', '').lower(),
                        'roll': player.get('Roll', ''),
                        'status': player.get('Status', ''),
                        'points': leaderboard.get(player.get('Name', '').lower(), {}).get('points', 0),
                        'Chaos coins': player.get('Chaos coins', '0')
                    }
                    all_players.append(player_data)

            # Sort by points descending
            all_players.sort(key=lambda x: x['points'], reverse=True)

            # Draw player cards
            for i, player in enumerate(all_players[:16]):  # Limit to top 16
                # Card background
                card_width = 700
                card_height = 120
                card_x = (width - card_width) // 2
                card_y = y_position

                # Shadow effect
                shadow = Image.new('RGBA', (card_width + 10, card_height + 10), (0, 0, 0, 0))
                shadow_draw = ImageDraw.Draw(shadow)
                shadow_draw.rounded_rectangle((5, 5, card_width + 5, card_height + 5), 
                                             radius, fill=(0, 0, 0, 100))
                shadow = shadow.filter(ImageFilter.GaussianBlur(5))
                img.paste(shadow, (card_x - 5, card_y - 5), shadow)

                # Card background
                draw.rounded_rectangle((card_x, card_y, card_x + card_width, card_y + card_height),
                                      radius, fill=(50, 50, 70))

                # Position indicator
                position = f"{i+1}."
                position_color = (255, 215, 0) if i < 3 else (220, 220, 220)  # Gold for top 3
                position_bbox = draw.textbbox((0, 0), position, font=player_font)
                position_x = card_x + 25  # 25px from left edge
                position_y = card_y + (card_height // 2) - (position_bbox[3] // 2)  # Vertically centered
                draw.text((position_x, position_y), position, fill=position_color, font=player_font)

                # 1. Player Name (x=0, y=ymax/2 -> middle-left)
                team_color = team_colors.get(player['team'], (220, 220, 220))
                name_bbox = draw.textbbox((0, 0), player['name'], font=player_font)
                name_x = position_x + position_bbox[2] + 15  # 15px after position number
                name_y = card_y + (card_height // 2) - (name_bbox[3] // 2)  # Vertically centered
                draw.text((name_x, name_y), player['name'], fill=team_color, font=player_font)

                # Chaos Coin info
                print(player.get('Chaos coins', '0'))
                coins_text = f"Chaos Coins: {player.get('Chaos coins', '0')}"
                coins_bbox = draw.textbbox((0, 0), coins_text, font=stat_font)
                coins_x = card_x + card_width - coins_bbox[2] - 20  # 20px padding from right
                coins_y = card_y + card_height - coins_bbox[3] - 10  # 10px padding from bottom
                draw.text((coins_x, coins_y), coins_text, fill=(180, 180, 180), font=stat_font)

                # 2. Roll Info (x=xmax/2, y=ymax/2 -> absolute center)
                roll_text = f"Roll: {player['roll']}"
                roll_bbox = draw.textbbox((0, 0), roll_text, font=stat_font)
                roll_x = card_x + (card_width // 2) - (roll_bbox[2] // 2)
                roll_y = card_y + (card_height // 2) - (roll_bbox[3] // 2)
                draw.text((roll_x, roll_y), roll_text, fill=(180, 180, 180), font=stat_font)

                # Points
                points_text = f"Points: {player['points']}"
                points_bbox = draw.textbbox((0, 0), points_text, font=stat_font)
                points_x = card_x + card_width - points_bbox[2] - 20  # 20px padding from right
                points_y = card_y + 10  # 10px padding from top
                draw.text((points_x, points_y), points_text, fill=(220, 220, 180), font=stat_font)

                # Status effect if available - now in bottom left corner
                if player['status']:
                    status_text = f"Affliction: {player['status']}"
                    status_bbox = draw.textbbox((0, 0), status_text, font=stat_font)
                    # Position at bottom left with 20px padding from left and 10px from bottom
                    draw.text((card_x + 20, card_y + card_height - status_bbox[3] - 10), 
                             status_text, fill=(180, 220, 240), font=stat_font)

                y_position += card_height + card_margin

            # Crop unused space
            img = img.crop((0, 0, width, min(height, y_position + 50)))

            # Save to bytes
            img_bytes = io.BytesIO()
            img.save(img_bytes, format='PNG', quality=100)
            img_bytes.seek(0)
            return img_bytes
        except Exception as e:
            print(f"Error in generate_scoreboard_image: {e}")
            traceback.print_exc()
            raise

    async def parse_sheet_data(self):
        try:
            all_values = self.sheet.get_all_values()
            data = {
                'red_team': [],
                'blue_team': [],
                'green_team': [],
                'yellow_team': [],
                'leaderboard': []
            }

            current_section = None

            for row in all_values:
                if not row:
                    continue

                first_cell = row[0].strip().lower() if row[0] else ""
                
                if "red" in first_cell and "blue" in first_cell:
                    current_section = "red_blue"
                    continue
                elif "green" in first_cell and "yellow" in first_cell:
                    current_section = "green_yellow"
                    continue
                elif "leaderboard" in first_cell:
                    current_section = "leaderboard"
                    continue
                
                # Skip header rows
                if any(x in first_cell for x in ["team", "position", "name"]):
                    continue
                
                if current_section == "red_blue" and len(row) >= 3:
                    team = row[1].lower().strip() if len(row) > 1 else ""
                    player_data = {
                        'Name': row[0].strip(),
                        'Team': team,
                        'Roll': row[2].strip() if len(row) > 2 else "",
                        'Chaos coins': row[3].strip() if len(row) > 3 and row[3].strip() != "" else "0",
                        'Status': row[4].strip() if len(row) > 4 and row[4] else ""
                    }

                    if team == "red":
                        data['red_team'].append(player_data)
                    elif team == "blue":
                        data['blue_team'].append(player_data)

                elif current_section == "green_yellow" and len(row) >= 3:
                    team = row[1].lower().strip() if len(row) > 1 else ""
                    player_data = {
                        'Name': row[0].strip(),
                        'Team': team,
                        'Roll': row[2].strip() if len(row) > 2 else "",
                        'Chaos coins': row[3].strip() if len(row) > 3 and row[3].strip() != "" else "0",
                        'Status': row[4].strip() if len(row) > 4 and row[4] else ""
                    }

                    if team == "green":
                        data['green_team'].append(player_data)
                    elif team == "yellow":
                        data['yellow_team'].append(player_data)

                elif current_section == "leaderboard" and len(row) >= 4:
                    data['leaderboard'].append({
                        'Position': row[0].strip(),
                        'Team': row[1].lower().strip() if len(row) > 1 else "",
                        'Combatant': row[2].strip() if len(row) > 2 else "",
                        'Points': int(row[3]) if len(row) > 3 and row[3].strip().isdigit() else 0
                    })

            return data
        except Exception as e:
            print(f"Error in parse_sheet_data: {e}")
            traceback.print_exc()
            return {
                'red_team': [],
                'blue_team': [],
                'green_team': [],
                'yellow_team': [],
                'leaderboard': []
            }

    async def update_stats(self, interaction: discord.Interaction):
        try:
            await interaction.response.defer(ephemeral=True)
            
            data = await self.parse_sheet_data()
            img_bytes = await self.generate_scoreboard_image(data)
            file = discord.File(img_bytes, filename="battle_stats.png")
            
            if self.message_id and self.channel_id:
                channel = self.get_channel(self.channel_id)
                if channel:
                    try:
                        msg = await channel.fetch_message(self.message_id)
                        await msg.edit(attachments=[file])
                        await interaction.followup.send("Stats updated!", ephemeral=True)
                    except discord.NotFound:
                        await interaction.followup.send("Original message not found, creating new one...", ephemeral=True)
                        msg = await channel.send(file=file)
                        self.message_id = msg.id
                        self.channel_id = msg.channel.id
                        self.config_sheet.update([['message_id', str(msg.id)], ['channel_id', str(msg.channel.id)]])
                    except Exception as e:
                        print(f"Error updating message: {e}")
                        await interaction.followup.send("Error updating message, creating new one...", ephemeral=True)
                        msg = await channel.send(file=file)
                        self.message_id = msg.id
                        self.channel_id = msg.channel.id
                        self.config_sheet.update([['message_id', str(msg.id)], ['channel_id', str(msg.channel.id)]])
                else:
                    await interaction.followup.send("Channel not found, creating new message...", ephemeral=True)
                    msg = await interaction.channel.send(file=file)
                    self.message_id = msg.id
                    self.channel_id = msg.channel.id
                    self.config_sheet.update([['message_id', str(msg.id)], ['channel_id', str(msg.channel.id)]])
            else:
                msg = await interaction.channel.send(file=file)
                self.message_id = msg.id
                self.channel_id = msg.channel.id
                self.config_sheet.update([['message_id', str(msg.id)], ['channel_id', str(msg.channel.id)]])
                await interaction.followup.send("Created new stats board!", ephemeral=True)
        except Exception as e:
            print(f"Error in update_stats: {e}")
            traceback.print_exc()
            try:
                await interaction.followup.send("Failed to generate stats image. Check logs for details.", ephemeral=True)
            except:
                pass

    async def on_ready(self):
        await self.tree.sync()
        print(f'Logged in as {self.user} (ID: {self.user.id})')
        print('------')

bot = BattleStatsBot()

@bot.tree.command(name="update", description="Update the battle stats board")
async def update_command(interaction: discord.Interaction):
    await bot.update_stats(interaction)

@bot.tree.command(name="ping", description="Test if the bot is alive")
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message("Pong! 🏓")

@bot.tree.command(name="roll", description="Roll for yourself or your entire team")
@app_commands.describe(team="Optional: Specify a team to roll for all members")
async def roll_command(interaction: discord.Interaction, team: str = None):
    """
    Roll with your team's custom odds or roll for an entire team
    """
    try:
        await interaction.response.defer()
        
        # Get the player data from spreadsheet
        data = await bot.parse_sheet_data()
        
        if team:  # If a team was specified, roll for all members of that team
            team = team.lower()
            if team not in ['red', 'blue', 'green', 'yellow']:
                await interaction.followup.send("Invalid team! Please specify red, blue, green, or yellow.")
                return

            team_players = data.get(f"{team}_team", [])
            if not team_players:
                await interaction.followup.send(f"No players found in {team.capitalize()} Team!")
                return

            results = []
            for player in team_players:
                try:
                    min_roll, max_roll = map(int, player['Roll'].split('-'))
                except:
                    min_roll, max_roll = 100, 200  # Fallback if parsing fails

                roll_result = random.randint(min_roll, max_roll)
                
                # Find matching Discord member (checks if spreadsheet name is contained in Discord name)
                discord_member = None
                for member in interaction.guild.members:
                    if player['Name'].lower() in member.display_name.lower():
                        discord_member = member
                        break
                
                display_name = discord_member.display_name if discord_member else player['Name']
                results.append({
                    'name': display_name,
                    'result': roll_result,
                    'range': f"{min_roll}-{max_roll}"
                })

            # Format the team roll results
            team_emoji = EMOJIS.get(team, "🎲")
            response_lines = [f"Team Roll Results for {team_emoji} {team.capitalize()} Team:\n"]
            for result in results:
                response_lines.append(f"{result['name']}: {result['result']} ({result['range']})")
            
            await interaction.followup.send("\n".join(response_lines))
            
        else:  # Normal single-player roll
            # Find the player in the data
            player_name = interaction.user.display_name
            player_team = None
            roll_range = "100-200"  # Default range
            
            # Search all teams for the player (now checks if spreadsheet name is contained in Discord name)
            for team in ['red_team', 'blue_team', 'green_team', 'yellow_team']:
                for player in data.get(team, []):
                    if player['Name'].lower() in player_name.lower():
                        player_team = player['Team']
                        roll_range = player['Roll']
                        break
                if player_team:
                    break
            
            if not player_team:
                await interaction.followup.send(f"Couldn't find {player_name} in any team!", ephemeral=True)
                return
            
            # Parse roll range
            try:
                min_roll, max_roll = map(int, roll_range.split('-'))
            except:
                min_roll, max_roll = 100, 200
            
            # Generate random roll
            roll_result = random.randint(min_roll, max_roll)
            
            # Get team emoji
            team_emoji = EMOJIS.get(player_team, "🎲")
            
            # Create response
            response = (
                f"{player_name} used roll\n"
                f"@{player_name} has rolled a {roll_result} ({min_roll} - {max_roll})\n"
                f"{team_emoji} {player_team.capitalize()} Team"
            )
            
            await interaction.followup.send(response)
            
    except Exception as e:
        print(f"Error in roll command: {e}")
        traceback.print_exc()
        await interaction.followup.send("Something went wrong with the roll. Try again later.", ephemeral=True)

bot.run(os.getenv('DISCORD_TOKEN'))
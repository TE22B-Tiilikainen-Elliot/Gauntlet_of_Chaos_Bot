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
from typing import Dict, List, Optional, Union

# Load environment variables
load_dotenv()

# Constants
SHEET_NAME = "Gauntlet 3 Player Stats"
CONFIG_SHEET_NAME = "Config"
SCOPES = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
EMOJIS = {"red": "🔴", "blue": "🔵", "green": "🟢", "yellow": "🟡", "1st": "🥇", "2nd": "🥈", "3rd": "🥉"}
TEAMS = ['red', 'blue', 'green', 'yellow']
DEFAULT_ROLL_RANGE = (100, 200)
ACTIVE_SUBMISSIONS = {}

# Initialize Google Sheets client
creds = ServiceAccountCredentials.from_json_keyfile_name('credentials.json', SCOPES)
sheets_client = gspread.authorize(creds)

class ImageGenerator:
    """Handles all image generation tasks with original styling"""
    @staticmethod
    def create_card(draw, x: int, y: int, width: int, height: int, radius: int, img: Image.Image) -> None:
        """Draw a rounded rectangle card with shadow (original styling)"""
        # Shadow effect
        shadow = Image.new('RGBA', (width + 10, height + 10), (0, 0, 0, 0))
        shadow_draw = ImageDraw.Draw(shadow)
        shadow_draw.rounded_rectangle((5, 5, width + 5, height + 5), radius, fill=(0, 0, 0, 100))
        shadow = shadow.filter(ImageFilter.GaussianBlur(5))
        img.paste(shadow, (x - 5, y - 5), shadow)
        
        # Card background
        draw.rounded_rectangle((x, y, x + width, y + height), radius, fill=(50, 50, 70))

    @staticmethod
    def get_fonts() -> tuple:
        """Try to load preferred fonts with fallbacks (original font setup)"""
        try:
            title_font = ImageFont.truetype("Inter-Bold.ttf", 42)
            player_font = ImageFont.truetype("Inter-SemiBold.ttf", 32)
            stat_font = ImageFont.truetype("Inter-Regular.ttf", 28)
        except:
            try:
                title_font = ImageFont.truetype("arialbd.ttf", 42)
                player_font = ImageFont.truetype("arialbd.ttf", 32)
                stat_font = ImageFont.truetype("arial.ttf", 28)
            except:
                title_font = ImageFont.load_default(42)
                player_font = ImageFont.load_default(32)
                stat_font = ImageFont.load_default(28)
        return title_font, player_font, stat_font

class SheetManager:
    """Handles all Google Sheets operations"""
    def __init__(self):
        self.spreadsheet = sheets_client.open(SHEET_NAME)
        self.config_sheet = self.spreadsheet.worksheet(CONFIG_SHEET_NAME)
        self.current_sheet = None
        self.message_id = None
        self.channel_id = None
        self.load_config()

    def load_config(self) -> None:
        """Load configuration from the Config sheet"""
        config = {row[0].strip().lower(): row[1].strip() for row in self.config_sheet.get_all_values() if len(row) >= 2}
        
        self.message_id = int(config.get('message_id')) if config.get('message_id', '').isdigit() else None
        self.channel_id = int(config.get('channel_id')) if config.get('channel_id', '').isdigit() else None
        
        current_round = int(config.get('current_round', '1'))
        self.set_round(current_round)

    def set_round(self, round_number: int) -> None:
        """Switch to a different round worksheet"""
        try:
            self.current_sheet = self.spreadsheet.worksheet(f"Round {round_number}")
            self._update_config('current_round', str(round_number))
        except gspread.exceptions.WorksheetNotFound:
            raise ValueError(f"Worksheet 'Round {round_number}' not found")

    def _update_config(self, key: str, value: str) -> None:
        """Update a configuration value in the sheet"""
        config_values = self.config_sheet.get_all_values()
        row_index = next((i for i, row in enumerate(config_values) 
                         if row and row[0].strip().lower() == key.lower()), -1)

        if row_index >= 0:
            self.config_sheet.update(
                values=[[key, value]],
                range_name=f'A{row_index+1}'
            )
        else:
            self.config_sheet.append_row([key, value])

    def parse_data(self) -> Dict[str, List[Dict]]:
        """Parse all player data from the current sheet"""
        data = {f"{team}_team": [] for team in TEAMS}
        data['leaderboard'] = []
        current_section = None

        for row in self.current_sheet.get_all_values():
            if not row:
                continue

            first_cell = row[0].strip().lower()
            
            # Section detection
            if "red" in first_cell and "blue" in first_cell:
                current_section = "red_blue"
                continue
            elif "green" in first_cell and "yellow" in first_cell:
                current_section = "green_yellow"
                continue
            elif "leaderboard" in first_cell:
                current_section = "leaderboard"
                continue
            
            # Skip headers
            if any(x in first_cell for x in ["team", "position", "name"]):
                continue
            
            # Process player data
            if current_section in ["red_blue", "green_yellow"] and len(row) >= 3:
                team = row[1].lower().strip()
                if team not in TEAMS:
                    continue
                    
                player_data = {
                    'Name': row[0].strip(),
                    'Team': team,
                    'Roll': row[2].strip(),
                    'Chaos coins': row[3].strip() if len(row) > 3 and row[3].strip() else "0",
                    'Status': row[4].strip() if len(row) > 4 and row[4] else ""
                }
                data[f"{team}_team"].append(player_data)

            elif current_section == "leaderboard" and len(row) >= 4:
                data['leaderboard'].append({
                    'Position': row[0].strip(),
                    'Team': row[1].lower().strip(),
                    'Combatant': row[2].strip(),
                    'Points': int(row[3]) if row[3].strip().isdigit() else 0
                })

        return data

class BattleStatsBot(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
        self.sheet_manager = SheetManager()

    async def setup_hook(self):
        await self.tree.sync()
        print(f'Logged in as {self.user} (ID: {self.user.id})')

    async def generate_scoreboard(self, data: Dict) -> io.BytesIO:
        """Generate the scoreboard image with original styling"""
        try:
            # Image dimensions and setup
            width, height = 800, 2490
            img = Image.new('RGBA', (width, height), (30, 30, 40))
            draw = ImageDraw.Draw(img)
            
            # Font setup (original font loading)
            title_font, player_font, stat_font = ImageGenerator.get_fonts()

            # Title and subtitle (original styling)
            title = "Gauntlet of Chaos"
            subtitle = "Leaderboard"

            # Draw title (original positioning)
            title_bbox = draw.textbbox((0, 0), title, font=title_font)
            title_w = title_bbox[2] - title_bbox[0]
            draw.text(((width - title_w) / 2, 40), title, fill=(220, 180, 40), font=title_font)

            # Draw subtitle (original positioning)
            subtitle_bbox = draw.textbbox((0, 0), subtitle, font=title_font)
            subtitle_w = subtitle_bbox[2] - subtitle_bbox[0]
            draw.text(((width - subtitle_w) / 2, 90), subtitle, fill=(220, 220, 220), font=title_font)

            y_position = 160
            card_width, card_height = 700, 120
            card_margin = 20
            radius = 15

            # Team colors (original colors)
            team_colors = {
                'red': (255, 80, 80),
                'blue': (80, 80, 255),
                'green': (80, 220, 80),
                'yellow': (255, 220, 80)
            }

            # Process leaderboard data (original logic)
            leaderboard = {
                p['Combatant'].lower(): {
                    'position': p.get('Position', ''),
                    'team': p.get('Team', '').lower(),
                    'points': p.get('Points', 0)
                } for p in data.get('leaderboard', []) if 'Combatant' in p
            }

            # Combine and sort players (original logic)
            all_players = []
            for team in TEAMS:
                for player in data.get(f"{team}_team", []):
                    player_data = {
                        'name': player.get('Name', 'Unknown'),
                        'team': player.get('Team', '').lower(),
                        'roll': player.get('Roll', ''),
                        'status': player.get('Status', ''),
                        'points': leaderboard.get(player.get('Name', '').lower(), {}).get('points', 0),
                        'Chaos coins': player.get('Chaos coins', '0')
                    }
                    all_players.append(player_data)

            all_players.sort(key=lambda x: x['points'], reverse=True)

            # Draw player cards (original styling)
            for i, player in enumerate(all_players[:16]):  # Limit to top 16
                card_x = (width - card_width) // 2
                card_y = y_position

                # Create card with shadow (original effect)
                ImageGenerator.create_card(draw, card_x, card_y, card_width, card_height, radius, img)

                # Position indicator (original styling)
                position = f"{i+1}."
                position_color = (255, 215, 0) if i < 3 else (220, 220, 220)
                position_bbox = draw.textbbox((0, 0), position, font=player_font)
                position_x = card_x + 25
                position_y = card_y + (card_height // 2) - (position_bbox[3] // 2)
                draw.text((position_x, position_y), position, fill=position_color, font=player_font)

                # Player name (original positioning)
                team_color = team_colors.get(player['team'], (220, 220, 220))
                name_bbox = draw.textbbox((0, 0), player['name'], font=player_font)
                name_x = position_x + position_bbox[2] + 15
                name_y = card_y + (card_height // 2) - (name_bbox[3] // 2)
                draw.text((name_x, name_y), player['name'], fill=team_color, font=player_font)

                # Chaos Coins (original positioning)
                coins_text = f"Chaos Coins: {player.get('Chaos coins', '0')}"
                coins_bbox = draw.textbbox((0, 0), coins_text, font=stat_font)
                coins_x = card_x + card_width - coins_bbox[2] - 20
                coins_y = card_y + card_height - coins_bbox[3] - 10
                draw.text((coins_x, coins_y), coins_text, fill=(180, 180, 180), font=stat_font)

                # Roll Info (centered, original positioning)
                roll_text = f"Roll: {player['roll']}"
                roll_bbox = draw.textbbox((0, 0), roll_text, font=stat_font)
                roll_x = card_x + (card_width // 2) - (roll_bbox[2] // 2)
                roll_y = card_y + (card_height // 2) - (roll_bbox[3] // 2)
                draw.text((roll_x, roll_y), roll_text, fill=(180, 180, 180), font=stat_font)

                # Points (original positioning)
                points_text = f"Points: {player['points']}"
                points_bbox = draw.textbbox((0, 0), points_text, font=stat_font)
                points_x = card_x + card_width - points_bbox[2] - 20
                points_y = card_y + 10
                draw.text((points_x, points_y), points_text, fill=(220, 220, 180), font=stat_font)

                # Status effect (original positioning)
                if player['status']:
                    status_text = f"Affliction: {player['status']}"
                    status_bbox = draw.textbbox((0, 0), status_text, font=stat_font)
                    draw.text((card_x + 20, card_y + card_height - status_bbox[3] - 10), 
                             status_text, fill=(180, 220, 240), font=stat_font)

                y_position += card_height + card_margin

            # Crop unused space (original logic)
            img = img.crop((0, 0, width, min(height, y_position + 50)))

            # Save to bytes
            img_bytes = io.BytesIO()
            img.save(img_bytes, format='PNG', quality=100)
            img_bytes.seek(0)
            return img_bytes

        except Exception as e:
            print(f"Error generating scoreboard: {e}")
            traceback.print_exc()
            raise

    async def update_stats(self, interaction: discord.Interaction) -> None:
        """Update the stats message with current data"""
        try:
            await interaction.response.defer(ephemeral=True)
            
            data = self.sheet_manager.parse_data()
            img_bytes = await self.generate_scoreboard(data)
            file = discord.File(img_bytes, filename="battle_stats.png")
            
            if self.sheet_manager.message_id and self.sheet_manager.channel_id:
                channel = self.get_channel(self.sheet_manager.channel_id)
                if channel:
                    try:
                        msg = await channel.fetch_message(self.sheet_manager.message_id)
                        await msg.edit(attachments=[file])
                        await interaction.followup.send("Stats updated!", ephemeral=True)
                        return
                    except discord.NotFound:
                        pass

            # Create new message if needed
            channel = interaction.channel
            msg = await channel.send(file=file)
            self.sheet_manager.message_id = msg.id
            self.sheet_manager.channel_id = msg.channel.id
            self.sheet_manager._update_config('message_id', str(msg.id))
            self.sheet_manager._update_config('channel_id', str(msg.channel.id))
            
            await interaction.followup.send("Created new stats board!", ephemeral=True)

        except Exception as e:
            print(f"Error updating stats: {e}")
            traceback.print_exc()
            await interaction.followup.send("Failed to update stats. Check logs for details.", ephemeral=True)

bot = BattleStatsBot()

def has_permission(interaction: discord.Interaction) -> bool:
    
    # Check for "Agent of Chaos" role
    agent_role = discord.utils.get(interaction.user.roles, name="Agent of Chaos")
    print(interaction.user.roles)
    return agent_role is not None

@bot.tree.command(name="update", description="Update the battle stats board")
async def update_command(interaction: discord.Interaction):
    if not has_permission(interaction):
        await interaction.response.send_message("❌ This command is restricted to admins or Agents of Chaos only.", ephemeral=True)
        return
    await bot.update_stats(interaction)

@bot.tree.command(name="ping", description="Test if the bot is alive")
async def ping(interaction: discord.Interaction):
    if not has_permission(interaction):
        await interaction.response.send_message("❌ This command is restricted to admins or Agents of Chaos only.", ephemeral=True)
        return
    await interaction.response.send_message("Pong! 🏓")

@bot.tree.command(name="roll", description="Roll for yourself or your entire team")
@app_commands.describe(team="Optional: Specify a team to roll for all members")
async def roll_command(interaction: discord.Interaction, team: str = None):
    try:
        await interaction.response.defer()
        data = bot.sheet_manager.parse_data()
        
        if team:
            team = team.lower()
            if team not in TEAMS:
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
                    min_roll, max_roll = DEFAULT_ROLL_RANGE

                roll_result = random.randint(min_roll, max_roll)
                discord_member = next((m for m in interaction.guild.members if player['Name'].lower() in m.display_name.lower()), None)
                display_name = discord_member.display_name if discord_member else player['Name']
                
                results.append(f"{display_name}: {roll_result} ({min_roll}-{max_roll})")

            await interaction.followup.send(f"Team Roll Results for {EMOJIS.get(team, '🎲')} {team.capitalize()} Team:\n" + "\n".join(results))
            
        else:
            player_name = interaction.user.display_name
            player_data = next(
                (p for team in TEAMS 
                 for p in data.get(f"{team}_team", []) 
                 if p['Name'].lower() in player_name.lower()),
                None
            )

            if not player_data:
                await interaction.followup.send(f"Couldn't find {player_name} in any team!", ephemeral=True)
                return
            
            try:
                min_roll, max_roll = map(int, player_data['Roll'].split('-'))
            except:
                min_roll, max_roll = DEFAULT_ROLL_RANGE

            roll_result = random.randint(min_roll, max_roll)
            team_emoji = EMOJIS.get(player_data['Team'], "🎲")
            
            await interaction.followup.send(
                f"{player_name} used roll\n"
                f"@{player_name} has rolled a {roll_result} ({min_roll} - {max_roll})\n"
                f"{team_emoji} {player_data['Team'].capitalize()} Team"
            )
            
    except Exception as e:
        print(f"Error in roll command: {e}")
        traceback.print_exc()
        await interaction.followup.send("Something went wrong with the roll. Try again later.", ephemeral=True)

@bot.tree.command(name="round", description="Change the current round being displayed")
@app_commands.describe(round_number="The round number to switch to")
async def round_command(interaction: discord.Interaction, round_number: int):
    if not has_permission(interaction):
        await interaction.response.send_message("❌ This command is restricted to admins or Agents of Chaos only.", ephemeral=True)
        return
    try:
        await interaction.response.defer(ephemeral=True)
        bot.sheet_manager.set_round(round_number)
        await interaction.followup.send(f"Switched to Round {round_number}!", ephemeral=True)
    except ValueError as e:
        await interaction.followup.send(str(e), ephemeral=True)
    except Exception as e:
        print(f"Error in round command: {e}")
        traceback.print_exc()
        await interaction.followup.send("Failed to change rounds. Check logs for details.", ephemeral=True)

@bot.tree.command(name="answer", description="Submit an anonymous message")
@app_commands.describe(message="Your anonymous message")
async def anon_submit(interaction: discord.Interaction, message: str):
    """Handles anonymous submissions with in-channel confirmation"""
    ACTIVE_SUBMISSIONS[interaction.user.id] = message
    await interaction.response.send_message(
        "✅ Your message was submitted anonymously!",
        ephemeral=True
    )

@bot.tree.command(name="showsubmitted", description="Show users who submitted")
async def show_submitted(interaction: discord.Interaction):
    if not has_permission(interaction):
        await interaction.response.send_message("❌ This command is restricted to admins or Agents of Chaos only.", ephemeral=True)
        return
    
    if not ACTIVE_SUBMISSIONS:
        await interaction.response.send_message("No submissions yet!", ephemeral=True)
        return
    
    try:
        submitter_info = []
        for user_id in ACTIVE_SUBMISSIONS.keys():
            member = interaction.guild.get_member(user_id)
            if member:
                submitter_info.append(f"• {member.display_name}")
            else:
                try:
                    user = await bot.fetch_user(user_id)
                    submitter_info.append(f"• {user.name}")
                except:
                    submitter_info.append(f"• Unknown User ({user_id})")
        
        response = (
            f"📝 Submitted ({len(submitter_info)}):\n" +
            "\n".join(submitter_info)
        )
        
        await interaction.response.send_message(response, ephemeral=True)
        
    except Exception as e:
        error_msg = f"Error: {str(e)}"
        print(f"showsubmitted error: {error_msg}")
        await interaction.response.send_message(
            f"⚠️ Couldn't check submissions. Error: {error_msg}",
            ephemeral=True
        )

@bot.tree.command(name="showanswers", description="Reveal anonymous messages")
async def show_anon(interaction: discord.Interaction):
    if not has_permission(interaction):
        await interaction.response.send_message("❌ This command is restricted to admins or Agents of Chaos only.", ephemeral=True)
        return
    
    if not ACTIVE_SUBMISSIONS:
        await interaction.response.send_message("❌ No submissions yet!", ephemeral=True)
        return
    
    shuffled_messages = list(ACTIVE_SUBMISSIONS.items())
    random.shuffle(shuffled_messages)
    
    public_output = "🔍 **Anonymous Messages** 🔍\n" + "\n".join(
        f"`{i+1}.` {msg}" 
        for i, (_, msg) in enumerate(shuffled_messages)
    )
    
    admin_log = ["📜 **Author Mapping** 📜"]
    for i, (user_id, msg) in enumerate(shuffled_messages, 1):
        member = interaction.guild.get_member(user_id)
        if member:
            admin_log.append(f"`{i}.` 👤 {member.display_name}\n   ✉️ {msg}")
        else:
            try:
                user = await bot.fetch_user(user_id)
                admin_log.append(f"`{i}.` 👤 {user.name}\n   ✉️ {msg}")
            except:
                admin_log.append(f"`{i}.` 👤 Unknown User ({user_id})\n   ✉️ {msg}")
    
    await interaction.response.send_message(public_output)
    await interaction.followup.send(
        "\n".join(admin_log),
        ephemeral=True
    )
    
    ACTIVE_SUBMISSIONS.clear()

bot.run(os.getenv('DISCORD_TOKEN'))
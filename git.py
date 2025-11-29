#!/usr/bin/env python3
"""
Advanced GitHub Auto Contribution Script
- Multiple commits per day
- Backdate commits to fill contribution gaps
- GitHub API integration
- Customizable patterns
"""

import os
import subprocess
from datetime import datetime, timedelta
import random
import json
import requests

class GitHubAutoCommit:
    def __init__(self, repo_path, github_token=None, file_name="activity.txt"):
        """
        Initialize the auto commit script
        
        Args:
            repo_path: Path to your git repository
            github_token: GitHub personal access token (optional)
            file_name: Name of the file to update
        """
        self.repo_path = repo_path
        self.file_name = file_name
        self.file_path = os.path.join(repo_path, file_name)
        self.github_token = github_token
        
        self.activity_messages = [
            "Updated documentation",
            "Code review completed",
            "Bug fix implemented",
            "Performance optimization",
            "Feature enhancement",
            "Refactored code structure",
            "Added unit tests",
            "Updated dependencies",
            "Security patch applied",
            "UI improvements",
            "Database optimization",
            "API endpoint updated",
            "Configuration changes",
            "Dependency updates",
            "Code cleanup"
        ]
    
    def setup_repo(self):
        """Create the activity file if it doesn't exist"""
        if not os.path.exists(self.file_path):
            with open(self.file_path, 'w') as f:
                f.write("# GitHub Activity Log\n\n")
            print(f"✓ Created {self.file_name}")
    
    def add_activity(self, timestamp=None):
        """Add a new activity entry to the file"""
        if timestamp is None:
            timestamp = datetime.now()
        
        timestamp_str = timestamp.strftime("%Y-%m-%d %H:%M:%S")
        message = random.choice(self.activity_messages)
        
        with open(self.file_path, 'a') as f:
            f.write(f"[{timestamp_str}] {message}\n")
        
        return message
    
    def git_commit(self, message, date=None):
        """
        Stage changes and create a git commit
        
        Args:
            message: Commit message
            date: Custom date for the commit (datetime object)
        """
        try:
            os.chdir(self.repo_path)
            
            # Add the file
            subprocess.run(['git', 'add', self.file_name], check=True)
            
            # Prepare commit command
            commit_cmd = ['git', 'commit', '-m', message]
            
            # Add custom date if provided
            env = os.environ.copy()
            if date:
                date_str = date.strftime("%Y-%m-%d %H:%M:%S")
                env['GIT_AUTHOR_DATE'] = date_str
                env['GIT_COMMITTER_DATE'] = date_str
            
            subprocess.run(commit_cmd, env=env, check=True)
            
            date_info = f" (dated: {date.strftime('%Y-%m-%d')})" if date else ""
            print(f"✓ Commit created: {message}{date_info}")
            return True
            
        except subprocess.CalledProcessError as e:
            print(f"✗ Git error: {e}")
            return False
    
    def git_stash(self):
        """Stash current changes"""
        try:
            os.chdir(self.repo_path)
            subprocess.run(['git', 'stash'], check=True, capture_output=True)
            print("✓ Stashed local changes")
            return True
        except subprocess.CalledProcessError:
            return False
    
    def git_stash_pop(self):
        """Pop stashed changes"""
        try:
            os.chdir(self.repo_path)
            subprocess.run(['git', 'stash', 'pop'], check=True, capture_output=True)
            print("✓ Restored stashed changes")
            return True
        except subprocess.CalledProcessError:
            return False
    
    def git_pull(self):
        """Pull latest changes from remote repository"""
        try:
            os.chdir(self.repo_path)
            
            # Check if there are unstaged changes
            status = subprocess.run(['git', 'status', '--porcelain'], 
                                  capture_output=True, text=True, check=True)
            
            if status.stdout.strip():
                print("⚠ Found unstaged changes, stashing them...")
                self.git_stash()
                subprocess.run(['git', 'pull', '--rebase'], check=True)
                self.git_stash_pop()
            else:
                subprocess.run(['git', 'pull', '--rebase'], check=True)
            
            print("✓ Pulled latest changes")
            return True
        except subprocess.CalledProcessError as e:
            print(f"⚠ Pull warning: {e}")
            return False
    
    def git_push(self, force=False, auto_pull=True):
        """Push commits to remote repository"""
        try:
            os.chdir(self.repo_path)
            
            # Check if remote exists
            result = subprocess.run(['git', 'remote'], capture_output=True, text=True)
            if not result.stdout.strip():
                print("✗ No remote repository configured")
                return False
            
            # Get current branch
            branch_result = subprocess.run(['git', 'branch', '--show-current'],
                                         capture_output=True, text=True)
            current_branch = branch_result.stdout.strip() or 'main'
            
            # Try to push
            push_cmd = ['git', 'push']
            if force:
                push_cmd.extend(['--force', '--set-upstream', 'origin', current_branch])
            else:
                push_cmd.extend(['origin', current_branch])
            
            result = subprocess.run(push_cmd, capture_output=True, text=True)
            
            if result.returncode != 0:
                # Check if it's a non-fast-forward error
                if 'non-fast-forward' in result.stderr or 'rejected' in result.stderr:
                    if auto_pull and not force:
                        print("⚠ Repository is behind remote. Pulling changes...")
                        if self.git_pull():
                            # Try pushing again
                            subprocess.run(push_cmd, check=True)
                            print("✓ Changes pushed to GitHub")
                            return True
                        else:
                            print("✗ Failed to pull changes")
                            return False
                    else:
                        print("✗ Push rejected. Run 'git pull' first or enable auto_pull")
                        return False
                elif 'no upstream branch' in result.stderr:
                    # Set upstream and push
                    print(f"⚠ Setting upstream branch to origin/{current_branch}")
                    push_cmd = ['git', 'push', '--set-upstream', 'origin', current_branch]
                    if force:
                        push_cmd.insert(2, '--force')
                    subprocess.run(push_cmd, check=True)
                    print("✓ Changes pushed to GitHub")
                    return True
                else:
                    print(f"✗ Push error: {result.stderr}")
                    return False
            else:
                print("✓ Changes pushed to GitHub")
                return True
            
        except subprocess.CalledProcessError as e:
            print(f"✗ Push error: {e}")
            return False
    
    def create_multiple_commits(self, count=3, date=None):
        """
        Create multiple commits for a single day
        
        Args:
            count: Number of commits to create
            date: Date for commits (defaults to today)
        """
        if date is None:
            date = datetime.now()
        
        print(f"\nCreating {count} commits for {date.strftime('%Y-%m-%d')}...")
        
        for i in range(count):
            # Spread commits throughout the day
            hour = random.randint(9, 20)
            minute = random.randint(0, 59)
            commit_time = date.replace(hour=hour, minute=minute, second=0)
            
            message = self.add_activity(commit_time)
            self.git_commit(message, commit_time)
    
    def backfill_commits(self, days_back=30, commits_per_day_range=(1, 5), skip_weekends=False):
        """
        Create commits for past dates to fill contribution graph
        
        Args:
            days_back: How many days back to create commits
            commits_per_day_range: Tuple of (min, max) commits per day
            skip_weekends: Whether to skip Saturday and Sunday
        """
        print(f"\nBackfilling commits for the last {days_back} days...")
        
        today = datetime.now()
        
        for i in range(days_back):
            commit_date = today - timedelta(days=i)
            
            # Skip weekends if requested
            if skip_weekends and commit_date.weekday() >= 5:
                continue
            
            # Random number of commits for this day
            num_commits = random.randint(*commits_per_day_range)
            
            # 20% chance of no commits (more realistic pattern)
            if random.random() < 0.2:
                continue
            
            self.create_multiple_commits(num_commits, commit_date)
    
    def backfill_year(self, year, commits_per_day_range=(1, 5), skip_weekends=False):
        """
        Create commits for an entire year
        
        Args:
            year: The year to backfill (e.g., 2024, 2023, 2022)
            commits_per_day_range: Tuple of (min, max) commits per day
            skip_weekends: Whether to skip Saturday and Sunday
        """
        print(f"\n🚀 Backfilling commits for the entire year {year}...")
        
        start_date = datetime(year, 1, 1)
        end_date = datetime(year, 12, 31)
        
        current_date = start_date
        total_days = (end_date - start_date).days + 1
        commits_created = 0
        
        while current_date <= end_date:
            # Skip weekends if requested
            if skip_weekends and current_date.weekday() >= 5:
                current_date += timedelta(days=1)
                continue
            
            # Random number of commits for this day
            num_commits = random.randint(*commits_per_day_range)
            
            # 20% chance of no commits (more realistic pattern)
            if random.random() < 0.2:
                current_date += timedelta(days=1)
                continue
            
            self.create_multiple_commits(num_commits, current_date)
            commits_created += num_commits
            current_date += timedelta(days=1)
        
        print(f"\n✅ Completed! Created {commits_created} commits across {total_days} days in {year}")
    
    def backfill_date_range(self, start_date, end_date, commits_per_day_range=(1, 5), skip_weekends=False):
        """
        Create commits for a specific date range
        
        Args:
            start_date: Start date (datetime object or string 'YYYY-MM-DD')
            end_date: End date (datetime object or string 'YYYY-MM-DD')
            commits_per_day_range: Tuple of (min, max) commits per day
            skip_weekends: Whether to skip Saturday and Sunday
        """
        # Convert strings to datetime if needed
        if isinstance(start_date, str):
            start_date = datetime.strptime(start_date, '%Y-%m-%d')
        if isinstance(end_date, str):
            end_date = datetime.strptime(end_date, '%Y-%m-%d')
        
        print(f"\n🚀 Backfilling commits from {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}...")
        
        current_date = start_date
        total_days = (end_date - start_date).days + 1
        commits_created = 0
        
        while current_date <= end_date:
            # Skip weekends if requested
            if skip_weekends and current_date.weekday() >= 5:
                current_date += timedelta(days=1)
                continue
            
            # Random number of commits for this day
            num_commits = random.randint(*commits_per_day_range)
            
            # 20% chance of no commits (more realistic pattern)
            if random.random() < 0.2:
                current_date += timedelta(days=1)
                continue
            
            self.create_multiple_commits(num_commits, current_date)
            commits_created += num_commits
            current_date += timedelta(days=1)
        
        print(f"\n✅ Completed! Created {commits_created} commits across {total_days} days")
    
    def get_commit_history(self):
        """Get list of commits in the repository"""
        try:
            os.chdir(self.repo_path)
            result = subprocess.run(
                ['git', 'log', '--pretty=format:%H|%s|%ad', '--date=short', '--all'],
                capture_output=True, text=True, check=True
            )
            
            commits = []
            for line in result.stdout.strip().split('\n'):
                if line:
                    parts = line.split('|')
                    if len(parts) == 3:
                        commits.append({
                            'hash': parts[0],
                            'message': parts[1],
                            'date': parts[2]
                        })
            
            return commits
        except subprocess.CalledProcessError as e:
            print(f"✗ Error getting commit history: {e}")
            return []
    
    def remove_random_commits(self, percentage=20, filter_by_message=None):
        """
        Remove random commits from the repository
        
        Args:
            percentage: Percentage of commits to remove (1-100)
            filter_by_message: Only remove commits containing this text (optional)
        """
        print(f"\n🗑️  Removing {percentage}% of commits randomly...")
        
        # Get all commits
        commits = self.get_commit_history()
        
        if not commits:
            print("✗ No commits found")
            return False
        
        # Filter commits if needed
        if filter_by_message:
            commits = [c for c in commits if filter_by_message.lower() in c['message'].lower()]
            print(f"Found {len(commits)} commits matching '{filter_by_message}'")
        else:
            print(f"Found {len(commits)} total commits")
        
        # Calculate how many to keep (inverse)
        keep_percentage = 100 - percentage
        num_to_keep = max(1, int(len(commits) * keep_percentage / 100))
        
        print(f"Will keep {num_to_keep} commits ({keep_percentage}%)")
        print(f"Will remove {len(commits) - num_to_keep} commits ({percentage}%)")
        
        print("\n⚠️  WARNING: This will rewrite git history!")
        confirm = input("Continue? (yes/no): ").lower()
        
        if confirm != 'yes':
            print("Cancelled.")
            return False
        
        try:
            os.chdir(self.repo_path)
            
            # Create backup branch
            subprocess.run(['git', 'branch', 'backup-before-cleanup'], 
                         capture_output=True)
            print("✓ Created backup branch: backup-before-cleanup")
            
            # Randomly select commits to KEEP
            commits_to_keep = random.sample(commits, num_to_keep)
            keep_hashes = set(c['hash'] for c in commits_to_keep)
            
            print("\n🔨 Rebuilding git history (this will take a while)...")
            print("Creating new branch...")
            
            # Create new orphan branch
            subprocess.run(['git', 'checkout', '--orphan', 'temp_new_history'], 
                         check=True, capture_output=True)
            
            # Remove all files from staging
            subprocess.run(['git', 'rm', '-rf', '.'], 
                         capture_output=True)
            
            # Cherry-pick commits we want to keep (in reverse order to maintain history)
            all_hashes = [c['hash'] for c in reversed(commits)]
            
            processed = 0
            kept = 0
            for i, commit_hash in enumerate(all_hashes):
                if commit_hash in keep_hashes:
                    try:
                        result = subprocess.run(
                            ['git', 'cherry-pick', commit_hash],
                            capture_output=True
                        )
                        
                        if result.returncode == 0:
                            kept += 1
                        else:
                            # Try to continue on conflicts
                            subprocess.run(['git', 'cherry-pick', '--skip'], 
                                         capture_output=True)
                    except:
                        subprocess.run(['git', 'cherry-pick', '--abort'], 
                                     capture_output=True)
                
                processed += 1
                if processed % 100 == 0:
                    print(f"Progress: {processed}/{len(all_hashes)} commits processed, {kept} kept...")
            
            print(f"\n✅ Kept {kept} commits")
            
            # Switch back and replace main
            print("\n🔄 Replacing main branch...")
            current_branch = subprocess.run(['git', 'branch', '--show-current'],
                                          capture_output=True, text=True).stdout.strip()
            
            if current_branch == 'temp_new_history':
                # Delete old main and rename temp to main
                subprocess.run(['git', 'branch', '-D', 'main'], 
                             capture_output=True)
                subprocess.run(['git', 'branch', '-m', 'main'], check=True)
                
                print(f"✅ Successfully removed {len(commits) - kept} commits!")
                print("✓ Backup branch available: backup-before-cleanup")
                print("\n⚠️  To complete, force push:")
                print("   git push origin main --force")
                return True
            else:
                print("✗ Something went wrong with branch switching")
                return False
            
        except subprocess.CalledProcessError as e:
            print(f"✗ Error: {e}")
            # Try to recover
            subprocess.run(['git', 'checkout', 'main'], capture_output=True)
            subprocess.run(['git', 'branch', '-D', 'temp_new_history'], 
                         capture_output=True)
            return False
        except Exception as e:
            print(f"✗ Unexpected error: {e}")
            return False
    
    def thin_out_commits(self, target_percentage=50):
        """
        Thin out commits to make the pattern more natural
        Keeps approximately target_percentage of commits
        
        Args:
            target_percentage: Percentage of commits to keep (1-100)
        """
        percentage_to_remove = 100 - target_percentage
        return self.remove_random_commits(percentage_to_remove)
    
    def get_github_stats(self, username):
        """
        Get GitHub contribution stats using GitHub API
        
        Args:
            username: GitHub username
        """
        if not self.github_token:
            print("⚠ GitHub token not provided, skipping stats")
            return None
        
        headers = {
            'Authorization': f'token {self.github_token}',
            'Accept': 'application/vnd.github.v3+json'
        }
        
        try:
            # Get user events
            url = f'https://api.github.com/users/{username}/events'
            response = requests.get(url, headers=headers)
            
            if response.status_code == 200:
                events = response.json()
                print(f"\n✓ Recent activity: {len(events)} events")
                return events
            else:
                print(f"✗ API error: {response.status_code}")
                return None
                
        except Exception as e:
            print(f"✗ Error fetching stats: {e}")
            return None
    
    def create_contribution_pattern(self, pattern='consistent', weeks=4):
        """
        Create commits following a specific pattern
        
        Args:
            pattern: 'consistent', 'increasing', 'random', 'workdays'
            weeks: Number of weeks to fill
        """
        print(f"\nCreating '{pattern}' contribution pattern for {weeks} weeks...")
        
        today = datetime.now()
        days = weeks * 7
        
        for i in range(days):
            commit_date = today - timedelta(days=i)
            weekday = commit_date.weekday()
            
            if pattern == 'consistent':
                num_commits = random.randint(2, 4)
            elif pattern == 'increasing':
                num_commits = min(1 + (days - i) // 7, 8)
            elif pattern == 'random':
                num_commits = random.randint(0, 8)
            elif pattern == 'workdays':
                num_commits = random.randint(3, 6) if weekday < 5 else 0
            else:
                num_commits = random.randint(1, 3)
            
            if num_commits > 0:
                self.create_multiple_commits(num_commits, commit_date)


def main():
    """Main execution function"""
    
    # ===== CONFIGURATION =====
    REPO_PATH = r"/home/rohan/projects/data-engineering-pipeline"  # Change this!
    GITHUB_TOKEN = "token"  # Optional: Add your GitHub token for API features
    GITHUB_USERNAME = "rohansb10"  # Your GitHub username
    
    # ===== CREATE INSTANCE =====
    auto_commit = GitHubAutoCommit(REPO_PATH, GITHUB_TOKEN)
    auto_commit.setup_repo()
    
    # ===== CHOOSE YOUR MODE =====
    
    print("\n" + "="*50)
    print("GitHub Auto Contribution Script")
    print("="*50)
    print("\nSelect mode:")
    print("1. Single commit (today)")
    print("2. Multiple commits (today)")
    print("3. Backfill past days")
    print("4. Create contribution pattern")
    print("5. Get GitHub stats")
    print("6. Backfill entire year (2024, 2023, 2022, etc.)")
    print("7. Backfill custom date range")
    print("8. Remove random commits (make pattern more natural)")
    print("9. Thin out commits (keep only X%)")
    
    try:
        choice = input("\nEnter choice (1-9): ").strip()
        
        if choice == '1':
            # Single commit today
            message = auto_commit.add_activity()
            auto_commit.git_commit(message)
            auto_commit.git_push()
        
        elif choice == '2':
            # Multiple commits today
            count = int(input("How many commits? (1-10): "))
            auto_commit.create_multiple_commits(count)
            auto_commit.git_push()
        
        elif choice == '3':
            # Backfill
            days = int(input("How many days back? (1-365): "))
            skip_weekends = input("Skip weekends? (y/n): ").lower() == 'y'
            auto_commit.backfill_commits(days, commits_per_day_range=(1, 4), skip_weekends=skip_weekends)
            auto_commit.git_push()
        
        elif choice == '4':
            # Pattern
            print("\nPatterns: consistent, increasing, random, workdays")
            pattern = input("Choose pattern: ").lower()
            weeks = int(input("How many weeks? (1-52): "))
            auto_commit.create_contribution_pattern(pattern, weeks)
            auto_commit.git_push()
        
        elif choice == '5':
            # GitHub stats
            auto_commit.get_github_stats(GITHUB_USERNAME)
        
        elif choice == '6':
            # Backfill entire year
            year = int(input("Enter year to backfill (e.g., 2024, 2023, 2022): "))
            skip_weekends = input("Skip weekends? (y/n): ").lower() == 'y'
            min_commits = int(input("Minimum commits per day (1-5): ") or "1")
            max_commits = int(input("Maximum commits per day (2-10): ") or "4")
            
            print(f"\n⚠️  WARNING: This will create commits for all {365 if year != 2024 else 366} days of {year}")
            confirm = input("Are you sure? This will take a while! (yes/no): ").lower()
            
            if confirm == 'yes':
                auto_commit.backfill_year(year, commits_per_day_range=(min_commits, max_commits), skip_weekends=skip_weekends)
                print("\n⚠️  Now pushing to GitHub... This may take a while!")
                auto_commit.git_push()
            else:
                print("Cancelled.")
        
        elif choice == '7':
            # Custom date range
            print("\nEnter dates in format YYYY-MM-DD")
            start = input("Start date (e.g., 2023-01-01): ").strip()
            end = input("End date (e.g., 2023-12-31): ").strip()
            skip_weekends = input("Skip weekends? (y/n): ").lower() == 'y'
            min_commits = int(input("Minimum commits per day (1-5): ") or "1")
            max_commits = int(input("Maximum commits per day (2-10): ") or "4")
            
            auto_commit.backfill_date_range(start, end, commits_per_day_range=(min_commits, max_commits), skip_weekends=skip_weekends)
            print("\n⚠️  Now pushing to GitHub... This may take a while!")
            auto_commit.git_push()
        
        elif choice == '8':
            # Remove random commits
            print("\n🗑️  Remove Random Commits")
            print("This will randomly remove commits to make your pattern look more natural")
            percentage = int(input("What percentage to remove? (1-100): "))
            filter_msg = input("Only remove commits with specific text? (leave empty for all): ").strip()
            
            if auto_commit.remove_random_commits(percentage, filter_msg if filter_msg else None):
                push_now = input("\nForce push to GitHub now? (yes/no): ").lower()
                if push_now == 'yes':
                    auto_commit.git_push(force=True)
        
        elif choice == '9':
            # Thin out commits
            print("\n✂️  Thin Out Commits")
            print("This will keep only a percentage of commits for a more natural look")
            keep_percentage = int(input("What percentage to KEEP? (1-100): "))
            
            if auto_commit.thin_out_commits(keep_percentage):
                push_now = input("\nForce push to GitHub now? (yes/no): ").lower()
                if push_now == 'yes':
                    auto_commit.git_push(force=True)
        
        else:
            print("Invalid choice")
    
    except KeyboardInterrupt:
        print("\n\nOperation cancelled")
    except Exception as e:
        print(f"\n✗ Error: {e}")


if __name__ == "__main__":
    main()

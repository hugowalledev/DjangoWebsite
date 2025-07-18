# Generated by Django 5.2.1 on 2025-07-16 18:21

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('esport', '0013_champion_playerstats_champion'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='match',
            name='blue_team',
        ),
        migrations.RemoveField(
            model_name='match',
            name='red_team',
        ),
        migrations.RemoveField(
            model_name='player',
            name='team',
        ),
        migrations.RemoveField(
            model_name='playerstats',
            name='player',
        ),
        migrations.AddField(
            model_name='player',
            name='fullname',
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.CreateModel(
            name='Roster',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('year', models.PositiveIntegerField()),
                ('team', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='esport.team')),
                ('tournament', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='esport.tournament')),
            ],
        ),
        migrations.AddField(
            model_name='match',
            name='blue_roster',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='blue_matches', to='esport.roster'),
        ),
        migrations.AddField(
            model_name='match',
            name='red_roster',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='red_matches', to='esport.roster'),
        ),
        migrations.AlterField(
            model_name='match',
            name='loser',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='loser_team', to='esport.roster'),
        ),
        migrations.AlterField(
            model_name='match',
            name='winner',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='winner_team', to='esport.roster'),
        ),
        migrations.AlterField(
            model_name='prediction',
            name='predicted_winner',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='predicted_match_wins', to='esport.roster'),
        ),
        migrations.CreateModel(
            name='RosterPlayer',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('is_starter', models.BooleanField(default=True)),
                ('role', models.CharField(blank=True, max_length=32)),
                ('player', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='esport.player')),
                ('roster', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='roster_players', to='esport.roster')),
            ],
            options={
                'unique_together': {('roster', 'player')},
            },
        ),
        migrations.AddField(
            model_name='playerstats',
            name='roster_player',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='esport.rosterplayer'),
        ),
    ]

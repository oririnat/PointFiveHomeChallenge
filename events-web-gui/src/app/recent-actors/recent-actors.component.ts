import { Component, OnInit } from '@angular/core';
import { ActorSchema } from '../models';
import { environment } from 'src/environments/environment';

@Component({
  selector: 'app-recent-actors',
  templateUrl: './recent-actors.component.html',
  styleUrls: ['./recent-actors.component.css']
})
export class RecentActorsComponent implements OnInit {
  recent_actors: ActorSchema[] = [];

  constructor() {
    console.log('RecentActorsComponent constructor called');
  }

  ngOnInit() {
    console.log('RecentActorsComponent ngOnInit called');

    this.loadRecentActors();

    // run the loadRecentActors function every 5 seconds
    setInterval(() => {
      this.loadRecentActors();
    }, 5000);
  }

  loadRecentActors() {
    // Fetch the recent actors, /actors with the parameter limit and skip
    fetch(`${environment.backendBaseUrl}/actors/recent`)
      .then(response => response.json())
      .then(data => {
        console.log('Recent actors:', data);

        // sort the actors for consistency
        data.sort((a: ActorSchema, b: ActorSchema) => {
          return a.id - b.id;
        });
        this.recent_actors = data;
      })
      .catch(error => {
        console.log('Error fetching recent actors:', error);
      });
  }

}
